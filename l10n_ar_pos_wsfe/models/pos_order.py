import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = 'pos.order'

    invoice_journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Invoice Journal',
        copy=False,
    )
    is_wsfe = fields.Boolean(
        string='Is Electronic Invoice',
        copy=False,
    )

    def _export_for_ui(self, order):
        res = super(PosOrder, self)._export_for_ui(order)
        refunded_moves = order.refunded_order_ids.mapped('account_move')
        res['doc_origin'] = ', '.join(
            refunded_moves.mapped(lambda x: x.get_pretty_sequence())
        )
        return res

    @api.model
    def _order_fields(self, ui_order):
        res = super(PosOrder, self)._order_fields(ui_order)
        res['invoice_journal_id'] = ui_order['invoice_journal_id']
        res['is_wsfe'] = ui_order['inv_electronic_mode']
        return res

    def _prepare_invoice_vals(self):
        res = super(PosOrder, self)._prepare_invoice_vals()
        if self.invoice_journal_id:
            res['journal_id'] = self.invoice_journal_id.id
        fiscal_position = self.partner_id.property_account_position_id
        if fiscal_position:
            res['fiscal_position_id'] = fiscal_position.id
        if self.refunded_order_ids.account_move:
            res['associated_inv_ids'] = [
                (6, 0, self.refunded_order_ids.mapped('account_move').ids)
            ]
        return res

    def _hook_recompute_account_move(self, new_move):
        new_move._onchange_invoice_date()
        new_move.compute_perceptions()
        new_move._onchange_payment_term_date_invoice()
        new_move.select_default_voucher_type()
        return

    def _create_invoice(self, move_vals):
        res = super(PosOrder, self)._create_invoice(move_vals)
        self._hook_recompute_account_move(res)
        return res

    def _generate_pos_order_invoice(self):
        moves = self.env['account.move']

        for order in self:
            # Force company for all SUPERUSER_ID action
            if order.account_move:
                moves += order.account_move
                continue

            if not order.partner_id:
                raise UserError(_('Please provide a partner for the sale.'))

            move_vals = order._prepare_invoice_vals()
            new_move = order._create_invoice(move_vals)

            order.write({'account_move': new_move.id, 'state': 'invoiced'})
            afip_result = False
            if order.is_wsfe:
                afip_result = (
                    new_move.sudo()
                    .with_company(order.company_id)
                    ._validate_electronic_invoices()
                )
            if (order.is_wsfe and afip_result) or not (
                order.is_wsfe and afip_result
            ):
                new_move.sudo().with_company(order.company_id)._post()
                moves += new_move
                order._apply_invoice_payments()

        if not moves:
            return {}

        return {
            'name': _('Customer Invoice'),
            'view_mode': 'form',
            'view_id': self.env.ref('account.view_move_form').id,
            'res_model': 'account.move',
            'context': "{'move_type':'out_invoice'}",
            'type': 'ir.actions.act_window',
            'nodestroy': True,
            'target': 'current',
            'res_id': moves and moves.ids[0] or False,
        }
