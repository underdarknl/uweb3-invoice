#!/usr/bin/python
"""Request handlers for the uWeb3 warehouse inventory software"""

import os
from functools import partial

import uweb3
from uweb3.libs.mail import MailSender
from uweb3plugins.core.paginators.table import calc_total_pages

from invoices import basepages
from invoices.common.decorators import NotExistsErrorCatcher, ParseView, loggedin
from invoices.common.helpers import FormFactory
from invoices.invoice import forms, helpers, model, tables, views
from invoices.invoice.decorators import WarehouseRequestWrapper


def to_list_wrapper(f, *args, **kwargs):
    """Wrapper for partial to make it return a list"""
    return [f(*args, **kwargs)]


class WarehouseAPIException(Exception):
    """Error that was raised during an API call to warehouse."""


class PageMaker(basepages.PageMaker):
    TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.warehouse_api_url = self.config.options["general"]["warehouse_api"]
        self.warehouse_apikey = self.config.options["general"]["apikey"]
        self.warehouse_connection = {
            "url": self.warehouse_api_url,
            "apikey": self.warehouse_apikey,
        }
        self.forms = FormFactory()
        self.forms.register_form(
            "new_invoice_form",
            helpers.InvoiceServiceBuilder(
                forms.InvoiceForm,
                client_method=partial(
                    to_list_wrapper, model.Client.FromClientNumber, self.connection
                ),
            ),
        )

    @loggedin
    @uweb3.decorators.checkxsrf
    @ParseView
    def RequestInvoicesPage(self):
        result, total_items, page = model.Invoice.IntergratedTable(
            connection=self.connection,
            request_data=self.get,
            page_size=self.page_size,
            searchable=("sequenceNumber", "title", "dateCreated", "status"),
            default_sort=[("ID", True)],
        )
        table = tables.InvoiceTable(
            result,
            sort_by=self.get.getfirst("sort_by"),
            sort_direction=self.get.getfirst("sort_direction"),
            search_url="/invoices",
            page=page,
            total_pages=calc_total_pages(total_items, self.page_size),
            renderer=tables.RenderInvoiceTable(xsrf_token=self._Get_XSRF()),
            query=self.get.getfirst("query"),
        )

        return views.InvoicesOverview(
            invoices_table=table,
        )

    @loggedin
    @NotExistsErrorCatcher
    @uweb3.decorators.checkxsrf
    @ParseView
    def RequestNewInvoicePage(self, client_number):
        client = model.Client.FromClientNumber(self.connection, client_number)

        invoice_form: forms.InvoiceForm = self.forms.get_form(
            "new_invoice_form", client_number=client_number
        )  # type: ignore

        return views.CreateNewInvoice(
            client=client,
            vat_amount=client.get_vat,
            api_url=self.warehouse_api_url,
            apikey=self.warehouse_apikey,
            invoice_form=invoice_form,
            scripts=["/js/invoice.js"],
            styles=["/styles/popup.css"],
        )

    @loggedin
    @NotExistsErrorCatcher
    @uweb3.decorators.checkxsrf
    @WarehouseRequestWrapper
    def RequestCreateNewInvoicePage(self, client_number):
        # Check if client exists
        model.Client.FromClientNumber(self.connection, client_number)
        invoice_form: forms.InvoiceForm = self.forms.get_form(
            "new_invoice_form",
            self.post,
            client_number=client_number,
        )  # type: ignore

        if not invoice_form.validate():
            return self.RequestNewInvoicePage(client_number)

        invoice = model.Invoice.Create(self.connection, invoice_form.data)
        # TODO: When warehouse server is down we still want to send this
        # when the initial order creation fails.
        model.WarehouseOrder.Create(
            self.warehouse_connection,
            {
                "description": invoice["client"]["name"],
                "status": invoice["status"],
                "reference": invoice["sequenceNumber"],
                "products": [
                    {"product_sku": p["product_sku"], "quantity": p["quantity"]}
                    for p in invoice_form.products.data
                ],
            },
        )

        mollie_request_url = None
        if mollie_amount := invoice_form.mollie_payment_request.data:
            mollie_request_url = helpers.create_mollie_request(
                invoice, mollie_amount, self.connection, self.options["mollie"]
            )

        if invoice["client"]["email"] and (
            invoice_form.send_mail.data or mollie_request_url
        ):
            self._send_mail(invoice["client"]["email"], invoice, mollie_request_url)
        return self.req.Redirect("/invoices", httpcode=303)

    def _send_mail(self, email: str, invoice: model.Invoice, mollie_request: str):
        mail_data = {}
        if mollie_request:
            mail_data["mollie"] = mollie_request

        pdf = helpers.to_pdf(
            self.RequestInvoiceDetails(invoice["sequenceNumber"]),
            filename="invoice.pdf",
        )

        with MailSender() as send_mail:
            send_mail.Attachments(
                recipients=email,
                subject="Your invoice",
                content=self.parser.Parse("email/invoice.txt", **mail_data),
                attachments=(pdf,),
            )

    @loggedin
    @ParseView
    @NotExistsErrorCatcher
    def RequestInvoiceDetails(self, sequence_number):
        invoice = model.Invoice.FromSequenceNumber(self.connection, sequence_number)
        return views.InvoiceDetails(
            title=f"Details invoice: {invoice['sequenceNumber']}",
            invoice=invoice,
            products=invoice.products,
            totals=invoice.Totals(),
        )

    @loggedin
    def RequestPDFInvoice(self, invoice):
        """Returns the invoice as a pdf file.

        Takes:
            invoice: int or str
        """
        requestedinvoice = self.RequestInvoiceDetails(invoice)
        if type(requestedinvoice) != uweb3.response.Redirect:
            return uweb3.Response(
                helpers.to_pdf(requestedinvoice), content_type="application/pdf"
            )
        return requestedinvoice

    @loggedin
    @uweb3.decorators.checkxsrf
    @NotExistsErrorCatcher
    def RequestInvoicePayed(self):
        """Sets the given invoice to paid."""
        invoice = self.post.getfirst("invoice")
        invoice = model.Invoice.FromSequenceNumber(self.connection, invoice)
        invoice.SetPayed()
        return self.req.Redirect("/invoices", httpcode=303)

    @loggedin
    @uweb3.decorators.checkxsrf
    @NotExistsErrorCatcher
    def RequestInvoiceReservationToNew(self):
        """Sets the given invoice to paid."""
        sequence_number = self.post.getfirst("invoice")
        invoice = model.Invoice.FromSequenceNumber(self.connection, sequence_number)

        model.WarehouseOrder.ConfirmReservation(
            self.warehouse_connection, {"reference": invoice["sequenceNumber"]}
        )
        invoice.ProFormaToRealInvoice()

        mail_data = {}
        content = self.parser.Parse("email/invoice.txt", **mail_data)
        updated_invoice = model.Invoice.FromPrimary(self.connection, invoice["ID"])
        pdf = helpers.to_pdf(
            self.RequestInvoiceDetails(updated_invoice["sequenceNumber"]),
            filename="invoice.pdf",
        )

        if updated_invoice["client"]["email"]:
            helpers.mail_invoice(
                updated_invoice["client"]["email"],
                subject="Your invoice",
                body=content,
                attachments=(pdf,),
            )
        return self.req.Redirect("/invoices", httpcode=303)

    @loggedin
    @uweb3.decorators.checkxsrf
    @NotExistsErrorCatcher
    @WarehouseRequestWrapper
    def RequestInvoiceCancel(self):
        """Sets the given invoice to paid."""
        invoice = self.post.getfirst("invoice")
        invoice = model.Invoice.FromSequenceNumber(self.connection, invoice)
        model.WarehouseOrder.Cancel(
            self.warehouse_connection, {"reference": invoice["sequenceNumber"]}
        )
        invoice.CancelProFormaInvoice()
        return self.req.Redirect("/invoices", httpcode=303)

    @loggedin
    @uweb3.decorators.checkxsrf
    @ParseView
    def RequestMt940(self, payments=[], failed_invoices=[]):
        return views.ImportMt940(
            payments=payments, failed_invoices=failed_invoices, mt940_preview=True
        )

    @loggedin
    @uweb3.decorators.checkxsrf
    def RequestUploadMt940(self):
        # TODO: File validation.
        payments = []
        failed_payments = []
        found_invoice_references = helpers.MT940_processor(
            self.files.getlist("fileupload")
        ).process_files()

        for invoice_ref in found_invoice_references:
            try:
                invoice = model.Invoice.FromSequenceNumber(
                    self.connection, invoice_ref["invoice"]
                )
            except (uweb3.model.NotExistError, Exception):
                # Invoice could not be found. This could mean two things,
                # 1. The regex matched something that looks like an invoice sequence
                # number, but it's not part of our system.
                # 2. The transaction contains a pro-forma invoice, but this invoice was
                # already set to paid and thus changed to a real invoice.
                # it's also possible that there was a duplicate pro-forma invoice ID in
                # the description, but since it was already processed no reference can
                # be found to it anymore.
                failed_payments.append(invoice_ref)
                continue

            platform = model.PaymentPlatform.FromName(
                self.connection, "ideal"
            )  # XXX: What payment platform is this?
            invoice.AddPayment(platform["ID"], invoice_ref["amount"])
            payments.append(invoice_ref)

        return self.RequestMt940(payments=payments, failed_invoices=failed_payments)