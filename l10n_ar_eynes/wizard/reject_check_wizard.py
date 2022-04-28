from odoo import fields, models, _
from odoo.addons import decimal_precision as dp


class RejectIssuedCheckWizard(models.TransientModel):
    _name = 'reject.issued.check.wizard'
    _description = 'Reject issued check wizard'

    reject_date = fields.Date('Reject date')
    note = fields.Text(string='Note')

    def action_reject(self):
        record_id = self._context.get('active_id')
        check = self.env['account.check'].browse(record_id)
        if check:
            check.reject_check(state='issued_check_state')


class RejectThirdPartyCheckWizard(models.TransientModel):
    _name = 'reject.third.party.check.wizard'
    _description = 'Reject third party check wizard'

    def _get_journal(self):
        user = self.env.user
        company_id = self.env.context.get('company_id', user.company_id.id)
        journal = self.env['account.journal'].search(
            [('company_id', '=', company_id), ('type', '=', 'sale')],
            limit=1
        )
        return journal and journal.id or False

    reject_date = fields.Date('Reject date')
    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Journal',
        required=True,
        default=_get_journal)

    expense_line_ids = fields.One2many(
        comodel_name='check.reject.expense',
        inverse_name='reject_id',
        string='Expenses')

    def action_reject(self):
        record_id = self._context.get('active_id')
        check = self.env['account.check'].browse(record_id)
        if check:
            check.reject_check(state='third_party_check_state')



class CheckRejectExpense(models.TransientModel):
    _name = 'check.reject.expense'
    _description = 'Reject Expense'

    reject_id = fields.Many2one(
        comodel_name='reject.third.party.check.wizard',
        string='Reject')

    product_id = fields.Many2one(
        comodel_name='product.product',
        string='Product',
        required=True)

    price = fields.Float(
        string='Amount',
        digits=dp.get_precision('Account'),
        required=True)
