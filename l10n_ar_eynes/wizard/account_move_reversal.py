from odoo import api, fields, models


class AccountMoveReversal(models.TransientModel):
    """
    Account move reversal wizard, it cancel an account move by reversing it.
    """

    def selection_vals(self):
        return [('refund', 'Partial Refund')]

    _inherit = 'account.move.reversal'
    refund_method = fields.Selection(
        selection=selection_vals,
        readonly=True,
        default='refund',
    )

    @api.model
    def default_get(self, fields):
        res = super(AccountMoveReversal, self).default_get(fields)
        if 'refund_method' in fields:
            res['refund_method'] = 'refund'
        return res

    def _get_voucher_type(self, move):
        return self.env['res.voucher.type'].search([
            ('denomination', '=', move.denomination),
            ('doc_type', '=', 'cn'),
            ('afip_code', '>' if move.is_FCE_invoice else '<', 200)
        ], limit=1)

    def _prepare_default_reversal(self, move):
        vals = super(AccountMoveReversal, self)._prepare_default_reversal(move)
        vals.update(
            {
                'associated_inv_ids': [move.id],
                'currency_id': move.currency_id.id,
                'currency_rate': move.currency_rate,
                'is_multi_currency': move.is_multi_currency,
                'voucher_type_id': self._get_voucher_type(move).id,
            }
        )
        return vals

    # def refund_moves(self):
    #     action = super(AccountMoveReversal, self).refund_moves()

    #     move_ids = action.get('res_id')
    #     if not move_ids:
    #         for domain in action.get('domain'):
    #             if domain[0] == 'id':
    #                 move_ids = domain[2]
    #     moves = self.env['account.move'].browse(move_ids)
    #     moves.with_context(is_reverse=True).compute_perceptions()

    #     return action
