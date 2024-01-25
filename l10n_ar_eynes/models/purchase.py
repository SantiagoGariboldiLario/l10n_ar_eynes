##############################################################################
#
#   Copyright (c) 2023-2024 Eynes SRL  (Eynes - Ingenieria del software)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
#
##############################################################################

import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def _prepare_invoice(self):
        """
        Add currency rate to invoice_vals
        (Allow to compute correctly amount fields)
        """
        invoice_vals = super(PurchaseOrder, self)._prepare_invoice()
        date_invoice = fields.Date.today()
        company = self.env.user.company_id
        company_currency = company.currency_id
        currency = self.currency_id
        if currency != company_currency:
            curr_rate = currency._get_currency_rate(company, date_invoice)
            if currency.preciated:
                currency_rate = curr_rate.inverse_company_rate
            else:
                currency_rate = curr_rate.company_rate
        else:
            currency_rate = 1.0

        invoice_vals['currency_rate'] = currency_rate
        return invoice_vals

    def action_view_invoice(self, invoices=False):
        res = super(PurchaseOrder, self).action_view_invoice(invoices=invoices)
        if not invoices:
            # Invoice_ids may be filtered depending on the user. To ensure we get all
            # invoices related to the purchase order, we read them in sudo to fill the
            # cache.
            self.sudo()._read(['invoice_ids'])
            invoices = self.invoice_ids

        for invoice in invoices:
            invoice._onchange_currency_id()

        return res
