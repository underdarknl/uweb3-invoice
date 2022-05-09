#!/usr/bin/python
"""Request handlers for the uWeb3 warehouse inventory software"""

# standard modules
from email.policy import default
from http import HTTPStatus
from itertools import zip_longest
from multiprocessing.sharedctypes import Value
import marshmallow
import requests
from marshmallow import Schema, fields, EXCLUDE, validate
from base.model.invoice import InvoiceProduct

from weasyprint import HTML
from io import BytesIO

# uweb modules
import uweb3
from base.decorators import NotExistsErrorCatcher, RequestWrapper, json_error_wrapper
from base.model import model
from base.pages.clients import RequestClientSchema


def ToPDF(html):
  """Returns a PDF based on the given HTML."""
  result = BytesIO()
  HTML(string=html).write_pdf(result)
  return result.getvalue()


class WarehouseAPIException(Exception):
  """Error that was raised during an API call to warehouse."""


class InvoiceSchema(Schema):

  class Meta:
    unknown = EXCLUDE

  client = fields.Int(required=True, allow_none=False)
  title = fields.Str(required=True, allow_none=False)
  description = fields.Str(required=True, allow_none=False)
  reservation = fields.Bool(required=True, allow_none=False)


class ProductSchema(Schema):
  name = fields.Str(required=True, allow_none=False)
  price = fields.Decimal(required=True, allow_nan=False)
  vat_percentage = fields.Int(required=True, allow_none=False)
  quantity = fields.Int(required=True, allow_none=False)


class ProductsCollectionSchema(Schema):

  class Meta:
    unknown = EXCLUDE

  products = fields.Nested(ProductSchema, many=True, required=True)


class CompanyDetailsSchema(Schema):

  class Meta:
    unknown = EXCLUDE

  name = fields.Str(required=True, allow_none=False)
  telephone = fields.Str(required=True, allow_none=False)
  address = fields.Str(required=True, allow_none=False)
  postalCode = fields.Str(
      required=True,
      allow_none=False,
      validate=validate.Regexp(
          r"^[1-9][0-9]{3} ?(?!sa|sd|ss|SA|SD|SS)[A-Za-z]{2}$",
          error="Should be 4 numbers and 2 letters"))
  city = fields.Str(required=True, allow_none=False)
  country = fields.Str(required=True, allow_none=False)
  vat = fields.Str(required=True, allow_none=False)
  kvk = fields.Str(required=True, allow_none=False)
  bankAccount = fields.Str(required=True, allow_none=False)
  bank = fields.Str(required=True, allow_none=False)
  bankCity = fields.Str(required=True, allow_none=False)
  invoiceprefix = fields.Str(required=True, allow_none=False)


class PageMaker:

  @uweb3.decorators.loggedin
  @uweb3.decorators.checkxsrf
  @uweb3.decorators.TemplateParser('invoices/invoices.html')
  def RequestInvoicesPage(self):
    return {
        'invoices': list(model.Invoice.List(self.connection)),
    }

  @uweb3.decorators.loggedin
  @uweb3.decorators.checkxsrf
  @RequestWrapper
  @uweb3.decorators.TemplateParser('invoices/create.html')
  def RequestNewInvoicePage(self, errors=[]):
    api_url = self.config.options['general']['warehouse_api']
    apikey = self.config.options['general']['apikey']
    response = requests.get(f'{api_url}/products?apikey={apikey}')
    json_response = response.json()
    if response.status_code != 200:
      if response.status_code == HTTPStatus.NOT_FOUND:
        return self.Error(
            f"Warehouse API at url '{api_url}' could not be found.")
      if response.status_code == HTTPStatus.FORBIDDEN:
        error = json_response.get(
            'error',
            'Not allowed to access this page. Are you using a valid apikey?')
        return self.Error(error)
      return self.Error("Something went wrong!")

    return {
        'clients': list(model.Client.List(self.connection)),
        'products': json_response['products'],
        'errors': errors,
        'api_url': api_url,
        'apikey': apikey,
        'scripts': ['/js/invoice.js']
    }

  @uweb3.decorators.loggedin
  @uweb3.decorators.checkxsrf
  def RequestCreateNewInvoicePage(self):
    # TODO: Handle validation errors
    products = []
    for product, price, vat, quantity in zip_longest(
        self.post.getlist('products'), self.post.getlist('invoice_prices'),
        self.post.getlist('invoice_vat'), self.post.getlist('quantity')):
      products.append({
          'name': product,
          'price': price,
          'vat_percentage': vat,
          'quantity': quantity
      })

    client = model.Client.FromClientNumber(self.connection,
                                           int(self.post.getfirst('client')))
    try:
      sanitized_invoice = InvoiceSchema().load({
          'client': client['ID'],
          'title': self.post.getfirst('title'),
          'description': self.post.getfirst('description'),
          'reservation': self.post.getfirst('reservation', False)
      })
      products = ProductsCollectionSchema().load({'products': products})
      self._handle_create(sanitized_invoice, products)
    except marshmallow.exceptions.ValidationError as error:
      return self.RequestNewInvoicePage(errors=[error.messages])
    except WarehouseAPIException as error:
      if 'errors' in error.args[0]:
        return self.RequestNewInvoicePage(errors=error.args[0]['errors'])
    return self.req.Redirect('/invoices', httpcode=303)

  @uweb3.decorators.loggedin
  @uweb3.decorators.checkxsrf
  @NotExistsErrorCatcher
  def RequestInvoicePayed(self):
    """Sets the given invoice to paid."""
    invoice = self.post.getfirst('invoice')
    invoice = model.Invoice.FromSequenceNumber(self.connection, invoice)
    invoice['status'] = 'paid'
    invoice.Save()
    return self.req.Redirect('/invoices', httpcode=303)

  @uweb3.decorators.ContentType('application/json')
  @json_error_wrapper
  def RequestInvoices(self):
    return {
        ' invoices': list(model.Invoice.List(self.connection)),
    }

  @uweb3.decorators.ContentType('application/json')
  @json_error_wrapper
  def RequestNewInvoice(self):
    client_number = RequestClientSchema().load(dict(self.post))
    sanitized_invoice = InvoiceSchema().load(dict(self.post))
    products = ProductsCollectionSchema().load(dict(self.post))

    client = model.Client.FromPrimary(self.connection, client_number['client'])
    sanitized_invoice['client'] = client['ID']

    invoice = self._handle_create(sanitized_invoice, products)
    return self.RequestInvoiceDetailsJSON(invoice['sequenceNumber'])

  @uweb3.decorators.TemplateParser('invoices/invoice.html')
  @NotExistsErrorCatcher
  def RequestInvoiceDetails(self, sequence_number):
    invoice = model.Invoice.FromSequenceNumber(self.connection, sequence_number)
    return {
        'invoice': invoice,
        'products': invoice.Products(),
        'totals': invoice.Totals()
    }

  @uweb3.decorators.ContentType('application/json')
  @json_error_wrapper
  def RequestInvoiceDetailsJSON(self, sequence_number):
    invoice = model.Invoice.FromSequenceNumber(self.connection, sequence_number)
    companydetails = {'companydetails': self.options.get('companydetails')}
    invoice.update(companydetails)
    return {
        'invoice': invoice,
        'products': list(invoice.Products()),
        'totals': invoice.Totals()
    }

  @uweb3.decorators.loggedin
  def RequestPDFInvoice(self, invoice):
    """Returns the invoice as a pdf file.

    Takes:
      invoice: int or str
    """
    requestedinvoice = self.RequestInvoiceDetails(invoice)
    if type(requestedinvoice) != uweb3.response.Redirect:
      return uweb3.Response(ToPDF(requestedinvoice),
                            content_type='application/pdf')
    return requestedinvoice

  def _handle_create(self, sanitized_invoice, products):
    api_url = self.config.options['general']['warehouse_api']
    api_key = self.config.options['general']['apikey']

    try:
      model.Client.autocommit(self.connection, False)
      invoice = model.Invoice.Create(self.connection, sanitized_invoice)
      for product in products['products']:
        product['invoice'] = invoice['ID']
        InvoiceProduct.Create(self.connection, product)
        response = requests.post(
            f'{api_url}/product/{product["name"]}/stock',
            json={
                "amount": -abs(product['quantity']),
                "reference": f"Invoice ID: {invoice['ID']}",
                "apikey": api_key
            })
        if response.status_code == 200:
          model.Client.commit(self.connection)
        else:
          model.Client.rollback(self.connection)
          raise WarehouseAPIException(response.json())
    except Exception:
      model.Client.rollback(self.connection)
      raise
    finally:
      model.Client.autocommit(self.connection, True)
    return invoice
