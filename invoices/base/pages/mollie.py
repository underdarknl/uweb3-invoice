#!/usr/bin/python
"""Html/JSON generators for api.coolmoo.se"""

__author__ = 'Jan Klopper <janklopper@underdark.nl>'
__version__ = '0.1'

import decimal
from invoices.base import decorators
from invoices.base.model.invoice import PRO_FORMA_PREFIX

import uweb3
from invoices.base.libs import mollie
from invoices.base.model import model


def round_price(d: decimal.Decimal):
  cents = decimal.Decimal('0.01')
  return d.quantize(cents, decimal.ROUND_HALF_UP)


class PageMaker(mollie.MollieMixin):
  """Holds all the html generators for the webapp

  Each page as a separate method.
  """

  # @uweb3.decorators.ContentType("application/json")
  # def RequestPaymentInfoMollieIdeal(self):
  #   mollie = self.NewMolliePaymentGateway()
  #   return {'issuers': mollie.GetIdealBanks()}

  # @uweb3.decorators.ContentType("application/json")
  # @json_error_wrapper
  # def RequestPaymentFormMollie(self):
  #   sequence_number = self.post.get('invoice')
  #   invoice = model.Invoice.FromSequenceNumber(self.connection, sequence_number)
  #   molliedata = self.RequestMollie(invoice)
  #   return molliedata

  def RequestMollie(self, invoice):
    price = invoice.Totals()['total_price']
    description = invoice.get('description')
    # TODO: Secret

    mollie = self.NewMolliePaymentGateway()
    return mollie.GetForm(
        invoice['ID'],
        price,  # Mollie expects amounts in euros  # TODO: (Jan) How should the currency be handled? Currently using a Decimal which is then converted to a string for mollie
        description,
        invoice['sequenceNumber'])

  def _Mollie_HookPaymentReturn(self, transaction):
    """This is the webhook that mollie calls when that transaction is updated."""
    # This route is used to receive updates from mollie about the transaction status.
    try:
      transaction = mollie.MollieTransaction.FromPrimary(
          self.connection, transaction)
      super()._Mollie_HookPaymentReturn(transaction['description'])

      updated_transaction = mollie.MollieTransaction.FromPrimary(
          self.connection, transaction)

      #  If the updated transactions status is paid and the status of the transaction was changed since the beginning of this route
      if updated_transaction[
          'status'] == mollie.MollieStatus.PAID and transaction[
              'status'] != updated_transaction['status']:
        invoice = model.Invoice.FromPrimary(self.connection,
                                            transaction['invoice'])
        invoice.SetPayed()

    except (uweb3.model.NotExistError, Exception) as e:
      # Prevent leaking data about transactions.
      uweb3.logging.error(
          f'Error triggered while processing mollie notification for transaction: {transaction} {e}'
      )
    finally:
      return 'ok'

  def _MollieHandleSuccessfulpayment(self, transaction):
    return 'ok'

  def _MollieHandleSuccessfulNotification(self, transaction):
    return 'ok'

  def _MollieHandleUnsuccessfulNotification(self, transaction, error):
    return 'ok'

  @decorators.NotExistsErrorCatcher
  @uweb3.decorators.TemplateParser('mollie/payment_ok.html')
  def Mollie_Redirect(self, transactionID):
    return