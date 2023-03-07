from odoo import models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _prepare_invoice(self):
        """Overriden to change journal
        for the first mathced journal from user_journal_rel table

        """
        invoice_vals = super()._prepare_invoice()
        partner = self.env['res.partner'].browse(invoice_vals['partner_id'])
        journal = self.env['user.journal.rel'].get_first_journal(partner)
        if journal:
            invoice_vals['journal_id'] = journal.id
        return invoice_vals
