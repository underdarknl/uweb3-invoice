# Standard modules
# Standard modules

import datetime
import decimal
from enum import Enum
import time

import pytz

# Custom modules
from invoices.base.model.model import RichModel, Client
from invoices.base.libs import modelcache
from invoices.base.pages.helpers.general import round_price

PAYMENT_PERIOD = datetime.timedelta(14)
PRO_FORMA_PREFIX = 'PF'


class InvoiceStatus(str, Enum):
  NEW = 'new'
  SENT = 'sent'
  PAID = 'paid'
  RESERVATION = 'reservation'
  CANCELED = 'canceled'


class Companydetails(modelcache.Record):
  """Abstraction class for companyDetails stored in the database."""

  @classmethod
  def HighestNumber(cls, connection):
    """Returns the ID for the newest companydetails."""
    with connection as cursor:
      number = cursor.Select(fields='max(ID) AS maxid',
                             table=cls.TableName(),
                             escape=False)
    if number:
      return number[0]['maxid']
    return 0


class InvoiceProduct(RichModel):
  """Abstraction class for Products that are linked to an invoice"""

  def Totals(self):
    """Read the price from the database and create the vat amount."""
    self['vat_amount'] = (self['price'] * self['quantity'] /
                          100) * self['vat_percentage']


class Invoice(RichModel):
  """Abstraction class for Invoices stored in the database."""

  _FOREIGN_RELATIONS = {
      'contract': None,
      'client': {
          'class': Client,
          'loader': 'FromPrimary',
          'LookupKey': 'ID'
      }
  }

  def _PreCreate(self, cursor):
    super(Invoice, self)._PreCreate(cursor)
    self['title'] = self['title'].strip(' ')[:80]

  def _PreSave(self, cursor):
    super(Invoice, self)._PreSave(cursor)
    self['title'] = self['title'].strip(' ')[:80]

  @classmethod
  def CalculateDateDue(self):
    return datetime.date.today() + PAYMENT_PERIOD

  @classmethod
  def FromSequenceNumber(cls, connection, seq_num):
    """Returns the invoice belonging to the given `sequence_number`."""
    safe_num = connection.EscapeValues(seq_num)
    with connection as cursor:
      invoice = cursor.Select(table=cls.TableName(),
                              conditions='sequenceNumber = %s' % safe_num)
    if not invoice:
      raise cls.NotExistError('There is no invoice with number %r.' % seq_num)
    return cls(connection, invoice[0])

  @classmethod
  def Create(cls, connection, record):
    """Creates a new invoice in the database and then returns it.

    Arguments:
      @ connection
        Database connection to use.
      @ record: mapping
        The Invoice record to create.

    Returns:
      Invoice: the newly created invoice.
    """
    status = record.get('status', InvoiceStatus.NEW.value)
    if status and status == InvoiceStatus.RESERVATION:
      record.setdefault('sequenceNumber', cls.NextProFormaNumber(connection))
    else:
      record.setdefault('sequenceNumber', cls.NextNumber(connection))
    record.setdefault('companyDetails',
                      Companydetails.HighestNumber(connection))
    record.setdefault('dateDue', cls.CalculateDateDue())
    return super(Invoice, cls).Create(connection, record)

  def ProFormaToRealInvoice(self):
    """Changes a pro forma invoice to an actual invoice.
    This changes the status to new, calculates a new date for when the invoice is due and generates a new sequencenumber.
    """
    self['sequenceNumber'] = self.NextNumber(self.connection)
    self['status'] = InvoiceStatus.NEW.value
    self['dateDue'] = self.CalculateDateDue()
    self.Save()

  def SetPayed(self):
    """Sets the current invoice status to paid. """
    if self._isProForma():
      self.ProFormaToRealInvoice()
    self['status'] = InvoiceStatus.PAID.value
    self.Save()

  def CancelProFormaInvoice(self):
    """Cancels a pro forma invoice"""
    if not self._isProForma():
      raise ValueError("Only pro forma invoices can be canceled.")
    self['status'] = InvoiceStatus.CANCELED.value
    self.Save()

  def _isProForma(self):
    return self['sequenceNumber'][:2] == PRO_FORMA_PREFIX

  @classmethod
  def NextNumber(cls, connection):
    """Returns the sequenceNumber for the next invoice to create."""
    with connection as cursor:
      current_max = cursor.Select(
          table=cls.TableName(),
          fields='sequenceNumber',
          conditions=[
              'YEAR(dateCreated) = YEAR(NOW())',
              'status not in ("reservation", "canceled")'
          ],
          limit=1,
          order=[('sequenceNumber', True)],
          escape=False)
    if current_max:
      year, sequence = current_max[0][0].split('-')
      return '%s-%03d' % (year, int(sequence) + 1)
    return '%s-%03d' % (time.strftime('%Y'), 1)

  @classmethod
  def NextProFormaNumber(cls, connection):
    """Returns the sequenceNumber for the next invoice to create."""
    with connection as cursor:
      current_max = cursor.Select(table=cls.TableName(),
                                  fields='sequenceNumber',
                                  conditions=[
                                      'YEAR(dateCreated) = YEAR(NOW())',
                                      'status in ("reservation", "canceled")'
                                  ],
                                  limit=1,
                                  order=[('sequenceNumber', True)],
                                  escape=False)
    if current_max:
      prefix, year, sequence = current_max[0][0].split('-')
      return '%s-%s-%03d' % (prefix, year, int(sequence) + 1)
    return '%s-%s-%03d' % (PRO_FORMA_PREFIX, time.strftime('%Y'), 1)

  @classmethod
  def List(cls, *args, **kwds):
    invoices = list(super().List(*args, **kwds))
    today = pytz.utc.localize(datetime.datetime.utcnow())
    for invoice in invoices:
      invoice['totals'] = invoice.Totals()
      invoice['dateDue'] = invoice['dateDue'].replace(
          tzinfo=datetime.timezone.utc)

      if today > invoice['dateDue'] and invoice['status'] != 'paid':
        invoice['overdue'] = 'overdue'
      else:
        invoice['overdue'] = ''
    return invoices

  def Totals(self):
    """Read the price from the database and create the vat amount."""
    with self.connection as cursor:
      totals = cursor.Select(
          table='invoiceProduct',
          fields=
          ('SUM(((price * quantity) / 100) * vat_percentage) + SUM(price * quantity) AS total',
           'SUM(price * quantity) as totalex'),
          conditions='invoice=%d' % self,
          escape=False)

    vatresults = []
    with self.connection as cursor:
      vatgroup = cursor.Select(
          table='invoiceProduct',
          fields=('vat_percentage',
                  'sum(((price * quantity) / 100) * vat_percentage) as total',
                  'sum(price * quantity) as taxable'),
          group='vat_percentage',
          conditions='invoice=%d' % self,
          escape=False)
    total_vat = 0
    for vat in vatgroup:
      total_vat = total_vat + vat['total']
      vatresults.append({
          'amount': round_price(vat['total']),
          'taxable': round_price(vat['taxable']),
          'type': vat['vat_percentage']
      })
    return {
        'total_price_without_vat': round_price(totals[0]['totalex']),
        'total_price': round_price(totals[0]['total']),
        'total_vat': round_price(total_vat),
        'vat': vatresults
    }

  def Products(self):
    """Returns all products that are part of this invoice."""
    products = InvoiceProduct.List(
        self.connection,
        conditions=['invoice=%d' % self])  # TODO (Stef) filter on not deleted
    index = 1
    for product in products:
      product['invoice'] = self
      product = InvoiceProduct(self.connection, product)
      product.Totals()
      product['index'] = index
      index = index + 1  # TODO implement loop indices in the template parser
      yield product

  def AddProducts(self, products):
    """Add multiple InvoiceProducts to an invoice.

    Arguments:
      @ products: [
                    { price: The price of the product,
                      vat_percentage: The amount of VAT that has to be paid over said product,
                      name: The name of the product
                      quantity: The amount of products
                    }
                  ]
    """
    for product in products:
      product['invoice'] = self[
          'ID']  # Set the product to the current invoice ID.
      InvoiceProduct.Create(self.connection, product)
