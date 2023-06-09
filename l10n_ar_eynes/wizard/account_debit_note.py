from odoo import fields, models


class AccountDebitNote(models.TransientModel):
    _inherit = 'account.debit.note'

    def default_journal(self):
        invoice_id = self._context.get('active_id')
        return self.env['account.move'].browse(invoice_id).journal_id.id

    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Use Specific Journal',
        help='If empty, uses the journal of the journal entry to be debited.',
        default=default_journal,
    )

    def _prepare_default_values(self, move):
        res = super(AccountDebitNote, self)._prepare_default_values(move)
        res['is_debit_note'] = True
        return res
