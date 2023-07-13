from odoo import fields, models


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

    def reverse_moves(self):
        action = super(AccountMoveReversal, self).reverse_moves()

        move_ids = action.get('res_id')
        if not move_ids:
            move_ids = action.get('domain')[2]
        moves = self.env['account.move'].browse(move_ids)
        moves.with_context(is_reverse=True).compute_perceptions()

        return action
