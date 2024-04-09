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

        # if electronic_invoices and internal_moves:
        #     raise UserError(
        #         _(
        #             "You can't validate Electronic and Internal invoices at the same time."
        #         )
        #     )
        # if electronic_invoices:
        #     invoices = electronic_invoices.sorted(key=lambda x: x.create_date)

        #     # La condicion para que se pueda validar un lote de
        #     # facturas electronicas es que deben ser del mismo Punto de Venta,
        #     # el mismo Tipo de Comprobante y obviamente estar en estado 'Draft'
        #     pos_ids = invoices.mapped('journal_id').ids
        #     # Son todas del mismo Punto de Venta?
        #     if len(set(pos_ids)) != 1:
        #         raise UserError(
        #             _(
        #                 'WSFE Error!\n'
        #                 'You are trying to validate several invoices but not all '
        #                 'of them belongs to the same point of sale'
        #             )
        #         )

        #     draft_state = map(lambda x: x.state == 'draft', invoices)
        #     # Estan todas en estado 'Draft'?
        #     if not all(draft_state):
        #         raise UserError(
        #             _(
        #                 "WSFE Error!\n"
        #                 "You are trying to validate several invoices but not "
        #                 "all of them are in 'draft' state"
        #             )
        #         )

        #     voucher_type = set(invoices.mapped('voucher_type_id'))
        #     # Son todas el mismo Tipo de Comprobante?
        #     if len(voucher_type) != 1:
        #         raise UserError(
        #             _(
        #                 'WSFE Error!\n'
        #                 "You are trying to validate several invoices but not all "
        #                 "of them are the same type. For example, all Customer "
        #                 "Invoices or all Customer Refund"
        #             )
        #         )

        (moves - electronic_invoices)._post(not self.force_post)
        for inv in sale_invoices - electronic_invoices:
            inv.write(
                {
                    'internal_number': inv.journal_id.get_sequence_from_invoice(
                        inv
                    )._next()
                }
            )
        afip_result = electronic_invoices._validate_electronic_invoices(
            not self.force_post
        )

        (sale_invoices - electronic_invoices)._compute_name()

        if afip_result is True:
            afip_result = {'type': 'ir.actions.act_window_close'}

        return afip_result
