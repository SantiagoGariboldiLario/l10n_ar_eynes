from odoo import models


class SaleAdvancePaymentInv(models.TransientModel):
    _inherit = "sale.advance.payment.inv"

    def _create_invoices(self, sale_orders):
        invoices = super()._create_invoices(sale_orders)
        for invoice in invoices:
            invoice._onchange_currency_id()
            invoice.with_company(invoice.company_id).add_perceptions()
        return invoices
