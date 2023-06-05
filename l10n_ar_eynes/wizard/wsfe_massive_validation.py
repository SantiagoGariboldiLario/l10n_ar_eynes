##############################################################################
#   Copyright (c) 2018 Eynes/E-MIPS (www.eynes.com.ar)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
##############################################################################

from odoo import _, models
from odoo.exceptions import UserError


class ValidateAccountMove(models.TransientModel):
    _inherit = "validate.account.move"
    _description = (
        "This wizard will confirm the all the selected draft invoices"
    )

    def validate_move(self):
        inv_obj = self.env['account.move']

        invoices = inv_obj.browse(self.env.context['active_ids'])
        invoices = invoices.filtered(lambda inv: inv.is_sale_document())

        if invoices:
            invoices = invoices.sorted(key=lambda x: x.create_date)

            # La condicion para que se pueda validar un lote de
            # facturas electronicas es que deben ser del mismo Punto de Venta,
            # el mismo Tipo de Comprobante y obviamente estar en estado 'Draft'
            pos_ids = invoices.mapped('journal_id').ids
            # Son todas del mismo Punto de Venta?
            if len(set(pos_ids)) != 1:
                raise UserError(
                    _(
                        'WSFE Error!\n'
                        'You are trying to validate several invoices but not all '
                        'of them belongs to the same point of sale'
                    )
                )

            draft_state = map(lambda x: x.state == 'draft', invoices)
            # Estan todas en estado 'Draft'?
            if not all(draft_state):
                raise UserError(
                    _(
                        "WSFE Error!\n"
                        "You are trying to validate several invoices but not "
                        "all of them are in 'draft' state"
                    )
                )

            voucher_type = set(invoices.mapped('voucher_type_id'))
            # Son todas el mismo Tipo de Comprobante?
            if len(voucher_type) != 1:
                raise UserError(
                    _(
                        'WSFE Error!\n'
                        "You are trying to validate several invoices but not all "
                        "of them are the same type. For example, all Customer "
                        "Invoices or all Customer Refund"
                    )
                )

            # Preparamos el lote de facturas para la AFIP
            next_system_number = invoices[0].get_highest_pos_sequence()

            request_log = invoices.action_post_from_massive(
                first_number=next_system_number
            )

            return {
                'name': _('WSFE Request'),
                'res_id': request_log.id,
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'wsfe.request',
                'type': 'ir.actions.act_window',
            }
        else:
            return super(ValidateAccountMove, self).validate_move()
