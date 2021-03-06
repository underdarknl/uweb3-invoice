from passlib.hash import pbkdf2_sha256
from uweb3 import model

__all__ = ["User", "Session"]


class User(model.Record):
    """Provides interaction to the user table"""

    @classmethod
    def IsFirstUser(cls, connection):
        with connection as cursor:
            return (
                cursor.Execute("""SELECT EXISTS(SELECT * FROM user) as user_exists;""")[
                    0
                ]["user_exists"]
                == 0
            )

    @classmethod
    def Create(cls, connection, record, generate_password_hash=False):
        if generate_password_hash:
            if len(record["password"]) < 8:
                raise ValueError("password too short, 8 characters minimal.")
            record["password"] = pbkdf2_sha256.hash(record["password"])
        return super().Create(connection, record)

    @classmethod
    def FromEmail(cls, connection, email, conditions=None):
        """Returns the user with the given email address.

        Arguments:
          @ connection: sqltalk.connection
            Database connection to use.
          @ email: str
            The email address of the user.

        Raises:
          NotExistError:
            The given user does not exist.

        Returns:
          User: user abstraction class.
        """
        if not conditions:
            conditions = []
        with connection as cursor:
            user = cursor.Select(
                table=cls.TableName(),
                conditions=[
                    "email=%s" % connection.EscapeValues(email),
                    'active = "true"',
                ]
                + conditions,
            )
        if not user:
            raise cls.NotExistError(
                "There is no user with the email address: %r" % email
            )
        return cls(connection, user[0])

    @classmethod
    def FromLogin(cls, connection, email, password):
        """Returns the user with the given login details."""
        user = list(
            cls.List(
                connection,
                conditions=(
                    "email = %s" % connection.EscapeValues(email),
                    'active = "true"',
                ),
            )
        )
        if not user:
            # fake a login attempt, and slow down, even though we know its never going
            # to end in a valid login, we dont want to let anyone know the account
            # does or does not exist.
            if connection.debug:
                print(
                    "password for non existant user would have been: ",
                    pbkdf2_sha256.hash(password),
                )
            raise cls.NotExistError("Invalid login, or inactive account.")
        if pbkdf2_sha256.verify(password, user[0]["password"]):
            return user[0]
        raise cls.NotExistError("Invalid password")

    def UpdatePassword(self, password):
        """Hashes the password and stores it in the database"""
        if len(password) < 8:
            raise ValueError("password too short, 8 characters minimal.")
        self["password"] = pbkdf2_sha256.hash(password)
        self.Save()

    def _PreCreate(self, cursor):
        super()._PreCreate(cursor)
        self["email"] = self["email"][:255]
        self["active"] = "true" if self["active"] == "true" else "false"

    def _PreSave(self, cursor):
        super()._PreSave(cursor)
        self["email"] = self["email"][:255]
        self["active"] = "true" if self["active"] == "true" else "false"

    def PasswordResetHash(self):
        """Returns a hash based on the user's ID, name and password."""
        return pbkdf2_sha256.hash(
            "%d%s%s" % (self["ID"], self["email"], self["password"]),
            salt=bytes(self["ID"]),
        )


class Session(model.SecureCookie):
    """Provides a model to request the secure cookie named 'session'"""
