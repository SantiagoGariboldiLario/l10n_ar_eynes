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
        partner = self.env['res.partner'].browse(invoice_vals['partner_id'])
        invoice_vals.update(
            {
                'address_shipping_id': self.partner_shipping_id.id,
            }
        )
        journal = self.env['user.journal.rel'].get_first_journal(partner)
        if journal:
            invoice_vals['journal_id'] = journal.id
        return invoice_vals

    @api.model
    def _create_invoices(self, grouped=False, final=False, date=None):
        invoice_ids = super(SaleOrder, self)._create_invoices(
            grouped,
            final,
            date=date,
        )
        invoices = self.env['account.move'].browse(invoice_ids)
        invoices._onchange_currency_id()
        return invoice_ids
