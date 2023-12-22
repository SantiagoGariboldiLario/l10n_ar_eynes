import logging

from odoo import api, fields, models

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
        return

    def _create_invoice(self, move_vals):
        res = super(PosOrder, self)._create_invoice(move_vals)
        self._hook_recompute_account_move(res)
        return res
