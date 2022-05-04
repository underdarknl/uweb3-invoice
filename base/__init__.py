"""A uWeb3 warehousing inventory software."""
import os
# Third-party modules
import uweb3

# Application
from . import basepages


def main():
  """Creates a uWeb3 application.

  The application is created from the following components:

  - The presenter class (PageMaker) which implements the request handlers.
  - The routes iterable, where each 2-tuple defines a url-pattern and the
    name of a presenter method which should handle it.
  - The execution path, internally used to find templates etc.
  """
  return uweb3.uWeb(
      basepages.PageMaker,
      [
          ('/', 'RequestIndex'),

          # # login / user management
          ('/login', 'HandleLogin', 'POST'),
          ('/login', 'RequestLogin'),
          ('/logout', 'RequestLogout'),
          ('/invoice/(.*)', 'RequestInvoiceDetails', 'GET'),
          ('/resetpassword', 'RequestResetPassword'),
          ('/resetpassword/([^/]*)/(.*)', 'RequestResetPassword'),
          ('/setup', 'RequestSetup'),

          #Invoices
          ('/invoices', 'Test', 'POST'),
          ('/invoices', 'RequestInvoicesPage', 'GET'),
          ('/invoices/new', 'RequestNewInvoicePage'),

          # API routes
          (f'{basepages.API_VERSION}/invoices', 'RequestInvoices', 'GET'),
          (f'{basepages.API_VERSION}/invoices', 'RequestNewInvoice', 'POST'),
          (f'{basepages.API_VERSION}/invoice/(.*)', 'RequestInvoiceDetailsJSON',
           'GET'),
          (f'{basepages.API_VERSION}/client/([0-9]+)', 'RequestClient'),
          (f'{basepages.API_VERSION}/clients', 'RequestClients', 'GET'),
          (f'{basepages.API_VERSION}/clients', 'RequestNewClient', 'POST'),
          (f'{basepages.API_VERSION}/clients/save', 'RequestSaveClient'),
          (f'{basepages.API_VERSION}(.*)', 'FourOhFour', 'POST'),

          # Helper files
          ('(/styles/.*)', 'Static'),
          ('(/js/.*)', 'Static'),
          ('(/media/.*)', 'Static'),
          ('(/favicon.ico)', 'Static'),
          ('(/.*)', 'RequestInvalidcommand'),
      ],
      os.path.dirname(__file__))
