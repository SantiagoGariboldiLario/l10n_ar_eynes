from odoo import api, models


class ReportInvoiceWithoutPayment(models.AbstractModel):
    _inherit = 'report.account.report_invoice'

    @api.model
    def _get_report_values(self, docids, data=None):
        rslt = super()._get_report_values(docids, data)
        docs = self.env['account.move'].browse(docids)

        qr_afip_urls = {}
        for invoice in docs:
            new_code_url = invoice.get_qr_code()
            if new_code_url:
                qr_afip_urls[invoice.id] = new_code_url

        rslt.update({'qr_code_afip': qr_afip_urls})

        return rslt
