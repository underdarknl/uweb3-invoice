import pytest
import datetime
from datetime import date
from decimal import Decimal

from tests.fixtures import *
from invoices.base.model import invoice

# XXX: Some parameters might seem like they are unused.
# However since they are pytest fixtures they are used to create a databaserecord
# that is needed for that specific test. Removing these paramters will fail the test
# as the record that is needed in the test database is no longer there.


def calc_due_date():
  return datetime.date.today() + invoice.PAYMENT_PERIOD


class TestClass:

  def test_validate_payment_period(self):
    assert invoice.PAYMENT_PERIOD == datetime.timedelta(14)

  def test_pro_forma_prefix(self):
    assert "PF" == invoice.PRO_FORMA_PREFIX

  def test_round_price(self):
    assert str(invoice.round_price(12.255)) == '12.26'
    assert str(invoice.round_price(12.26)) == '12.26'
    assert str(invoice.round_price(12.22)) == '12.22'

  def test_determine_invoice_type(self, create_invoice_object):
    pro_forma = create_invoice_object(
        status=invoice.InvoiceStatus.RESERVATION.value)
    real_inv = create_invoice_object(status=invoice.InvoiceStatus.NEW.value)

    assert pro_forma._isProForma() == True
    assert real_inv._isProForma() == False

  def test_create_invoice(self, connection, client_object,
                          companydetails_object):
    inv = invoice.Invoice.Create(
        connection, {
            'ID': 1,
            'title': 'test invoice',
            'description': 'test',
            'client': client_object['ID'],
            'status': 'new'
        })
    assert inv['ID'] == 1

  def test_invoice_sequence_number(self, connection, simple_invoice_dict):
    inv = invoice.Invoice.Create(connection, simple_invoice_dict)
    assert inv['sequenceNumber'] == f'{date.today().year}-001'

  def test_invoice_sequence_numbers(self, connection, simple_invoice_dict):
    inv1, inv2, inv3 = simple_invoice_dict.copy(), simple_invoice_dict.copy(
    ), simple_invoice_dict.copy()
    inv1['ID'] = 1
    inv2['ID'] = 2
    inv3['ID'] = 3

    inv1 = invoice.Invoice.Create(connection, inv1)
    inv2 = invoice.Invoice.Create(connection, inv2)
    inv3 = invoice.Invoice.Create(connection, inv3)
    assert inv1['sequenceNumber'] == f'{date.today().year}-001'
    assert inv2['sequenceNumber'] == f'{date.today().year}-002'
    assert inv3['sequenceNumber'] == f'{date.today().year}-003'

  def test_pro_forma_invoice_sequence_number(self, connection, client_object,
                                             companydetails_object):
    pro_forma = invoice.Invoice.Create(
        connection, {
            'ID': 1,
            'title': 'test invoice',
            'description': 'test',
            'client': client_object['ID'],
            'status': 'reservation'
        })
    assert pro_forma[
        'sequenceNumber'] == f'{invoice.PRO_FORMA_PREFIX}-{date.today().year}-001'

  def test_invoice_and_pro_forma_mix_sequence_number(self, connection,
                                                     client_object,
                                                     create_invoice_object):
    real_invoice = create_invoice_object(status=invoice.InvoiceStatus.NEW.value)
    pro_forma = create_invoice_object(
        status=invoice.InvoiceStatus.RESERVATION.value)
    second_real_invoice = create_invoice_object(
        status=invoice.InvoiceStatus.NEW.value)
    second_pro_forma = create_invoice_object(
        status=invoice.InvoiceStatus.RESERVATION.value)

    assert real_invoice['sequenceNumber'] == f'{date.today().year}-001'
    assert pro_forma[
        'sequenceNumber'] == f'{invoice.PRO_FORMA_PREFIX}-{date.today().year}-001'
    assert second_real_invoice['sequenceNumber'] == f'{date.today().year}-002'
    assert second_pro_forma[
        'sequenceNumber'] == f'{invoice.PRO_FORMA_PREFIX}-{date.today().year}-002'

  def test_datedue(self):
    assert calc_due_date() == invoice.Invoice.CalculateDateDue()

  def test_pro_forma_to_real_invoice(self, create_invoice_object):
    pro_forma = create_invoice_object(
        status=invoice.InvoiceStatus.RESERVATION.value)
    assert pro_forma['status'] == invoice.InvoiceStatus.RESERVATION

    pro_forma.ProFormaToRealInvoice()

    assert pro_forma['status'] == invoice.InvoiceStatus.NEW
    assert pro_forma['dateDue'] == calc_due_date()

  def test_invoice_to_paid(self, create_invoice_object):
    inv = create_invoice_object(status=invoice.InvoiceStatus.NEW.value)
    assert inv['status'] == invoice.InvoiceStatus.NEW

    inv.SetPayed()

    assert inv['status'] == invoice.InvoiceStatus.PAID
    assert inv['dateDue'] == calc_due_date()

  def test_pro_forma_to_paid(self, create_invoice_object):
    pro_forma = create_invoice_object(
        status=invoice.InvoiceStatus.RESERVATION.value)
    assert pro_forma['status'] == invoice.InvoiceStatus.RESERVATION

    pro_forma.SetPayed()

    assert pro_forma['sequenceNumber'] == f'{date.today().year}-001'
    assert pro_forma['status'] == invoice.InvoiceStatus.PAID
    assert pro_forma['dateDue'] == calc_due_date()

  def test_pro_forma_to_canceled(self, create_invoice_object):
    pro_forma = create_invoice_object(
        status=invoice.InvoiceStatus.RESERVATION.value)
    pro_forma.CancelProFormaInvoice()

    assert pro_forma['status'] == invoice.InvoiceStatus.CANCELED
    # Make sure the sequenceNumber is still a pro forma sequenceNumber
    assert pro_forma[
        'sequenceNumber'] == f'{invoice.PRO_FORMA_PREFIX}-{date.today().year}-001'

  def test_real_invoice_to_canceled(self, create_invoice_object):
    inv = create_invoice_object(status=invoice.InvoiceStatus.NEW.value)
    with pytest.raises(ValueError) as excinfo:
      inv.CancelProFormaInvoice()
    assert "Only pro forma invoices can be canceled" in str(excinfo)

  def test_add_invoice_products(self, create_invoice_object):
    inv = create_invoice_object(status=invoice.InvoiceStatus.NEW.value)
    inv.AddProducts([
        {
            'name': 'dakpan',
            'price': 10,
            'vat_percentage': 100,
            'quantity': 2
        },
        {
            'name': 'paneel',
            'price': 5,
            'vat_percentage': 100,
            'quantity': 10
        },
    ])
    products = list(inv.Products())
    assert len(products) == 2

  def test_invoice_with_products(self, connection, simple_invoice_dict):
    inv = invoice.Invoice.Create(connection, simple_invoice_dict)
    products = [
        {
            'name': 'dakpan',
            'price': 10,
            'vat_percentage': 100,
            'quantity': 2
        },
        {
            'name': 'paneel',
            'price': 5,
            'vat_percentage': 100,
            'quantity': 10
        },
    ]
    inv.AddProducts(products)

    result = inv.Totals()
    assert result['total_price_without_vat'] == 70  # 2*10 + 5*10
    assert result['total_price'] == 140  # 2(2*10 + 5*10)
    assert result['total_vat'] == 70

  def test_invoice_with_products_decimal(self, connection, simple_invoice_dict):
    inv = invoice.Invoice.Create(connection, simple_invoice_dict)
    products = [
        {
            'name': 'dakpan',
            'price': 100.34,
            'vat_percentage': 20,
            'quantity': 10  # 1204.08
        },
        {
            'name': 'paneel',
            'price': 12.25,
            'vat_percentage': 10,
            'quantity': 10  # 134.75
        },
    ]
    inv.AddProducts(products)

    result = inv.Totals()
    assert result['total_price_without_vat'] == invoice.round_price(
        Decimal(1125.90))
    assert result['total_price'] == invoice.round_price(1338.83)
    assert result['total_vat'] == invoice.round_price(212.93)

  def test_invoice_add_payment(self, connection, create_invoice_object):
    inv = create_invoice_object(status=invoice.InvoiceStatus.NEW.value)
    products = [
        {
            'name': 'dakpan',
            'price': 25,
            'vat_percentage': 10,
            'quantity': 10
        },
    ]
    inv.AddProducts(products)
    platform = invoice.PaymentPlatform.FromName(connection, 'contant')
    inv.AddPayment(platform['ID'], 10)
    platform = invoice.PaymentPlatform.FromName(connection, 'ideal')
    inv.AddPayment(platform['ID'], 20)
    payments = inv.GetPayments()
    assert len(payments) == 2
    assert payments[0]['platform']['name'] == 'contant'
    assert payments[0]['invoice']['ID'] == inv['ID']
    assert payments[0]['amount'] == 10
    assert payments[1]['amount'] == 20
    assert payments[1]['platform']['name'] == 'ideal'

  def test_invoice_add_payment_roundup(self, default_invoice_and_products):
    inv = default_invoice_and_products(status=invoice.InvoiceStatus.NEW.value)

    values = [10.01, 20.05, 9.001, 100.006, 9000.005, 1.004]
    for amount in values:
      inv.AddPayment(1, amount)

    payments = inv.GetPayments()
    for i in range(len(values)):
      assert payments[i]['amount'] == invoice.round_price(values[i])

  def test_set_invoice_paid_when_invoice_price_paid(
      self, connection, default_invoice_and_products):
    inv = default_invoice_and_products(status=invoice.InvoiceStatus.NEW.value)
    inv.AddPayment(1, 274.99)
    inv = invoice.Invoice.FromPrimary(connection, inv['ID'])

    # Status should not be changed as the total amount paid is not yet the amount required.
    assert inv['status'] == invoice.InvoiceStatus.NEW

    inv.AddPayment(1, 0.01)

    # Re-fetch from database to see if status has been changed propperly
    inv = invoice.Invoice.FromPrimary(connection, inv['ID'])
    assert inv['status'] == invoice.InvoiceStatus.PAID

  def test_do_not_uncancel_invoice_when_full_price_paid(
      self, connection, default_invoice_and_products):
    """Ensure that a canceled invoice is not uncanceled if payments are added to it that fullfill the required price.
    This is important because when a invoice is canceled the parts required are refunded to warehouse, if for some reason
    the invoice gets uncanceled the parts can be refunded again leading to duplicate refunds.
    """
    inv = default_invoice_and_products(
        status=invoice.InvoiceStatus.RESERVATION.value)
    inv.CancelProFormaInvoice()
    inv.AddPayment(1, 1000)
    inv = invoice.Invoice.FromPrimary(connection, inv['ID'])
    assert inv['status'] == invoice.InvoiceStatus.CANCELED

  def test(self):
    """Empty test to ensure that all data is truncated from the database."""
    pass
