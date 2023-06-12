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
