##############################################################################
#
#   Copyright (c) 2022-2023 Eynes SRL  (Eynes - Ingenieria del software)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
#
##############################################################################

import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _prepare_invoice(self):
        """Overriden to change journal
        for the first mathced journal from user_journal_rel table

        """
        invoice_vals = super()._prepare_invoice()
        invoice_vals.update(
            {
                'address_shipping_id': self.partner_shipping_id.id,
            }
        )
        journals = self.env.user.journal_ids
        if journals:
            invoice_vals['journal_id'] = journals[0].id
        return invoice_vals

    @api.model
    def _create_invoices(self, grouped=False, final=False, date=None):
        invoice_ids = super(SaleOrder, self)._create_invoices(
            grouped,
            final,
            date=date,
        )
        for invoice in invoice_ids:
            invoice._onchange_currency_id()
        return invoice_ids
