##############################################################################
#   Copyright (c) 2018 Eynes/E-MIPS (www.eynes.com.ar)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
##############################################################################

from odoo import models


class ValidateAccountMove(models.TransientModel):
    _inherit = "validate.account.move"
    _description = (
        "This wizard will confirm the all the selected draft invoices"
    )

    def validate_move(self):
        AccountMove = self.env['account.move']

        moves = AccountMove.browse(self.env.context['active_ids'])
        sale_invoices = moves.filtered(lambda inv: inv.is_sale_document())
        electronic_invoices = sale_invoices.filtered(
            lambda inv: inv.fiscal_type == 'electronic'
        )

        (moves - electronic_invoices)._post(not self.force_post)

        afip_result = electronic_invoices._validate_electronic_invoices(
            not self.force_post
        )

        if afip_result is True:
            afip_result = {'type': 'ir.actions.act_window_close'}

        return afip_result
