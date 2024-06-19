from odoo import _, fields, models
from odoo.exceptions import UserError, ValidationError


class RejectIssuedCheckWizard(models.TransientModel):
    _name = 'reject.issued.check.wizard'
    _description = 'Reject issued check wizard'

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    generate_rejection_journal_entry = fields.Boolean(
        string='Generate Rejection Journal Entry', default=True
    )  # Este campo queda deprecado a partir del 9/5/24, aparentemente SIEMPRE se genera el asiento
    reject_date = fields.Date(string='Reject date')
    reject_reason = fields.Text()

    def action_reject(self):
        """
        This method is called when the rejection is confirmed in the wizard.
        It change the state of the issued check to 'rejected' and also creates a move.
        """
        check = self.env['account.check'].browse(self._context.get('active_id'))

        if check:
            AccountMoveLine = self.env['account.move.line']

            if check.issued_check_state != 'debited':
                raise UserError(_('ERROR! This check is not Debited!'))

            config = self.env['account.check.config'].search(
                [('company_id', '=', check.company_id.id)]
            )
            if not config:
                raise ValidationError(
                    _(
                        'ERROR! There is no check configuration for this Company!'
                    )
                )

            move_ref = _(
                'Reject Check %(check_number)s', check_number=check.number
            )

            journal = config.deferred_journal_id

            move_id = self.env['account.move'].create(
                {
                    'journal_id': journal.id,
                    'date': self.reject_date,
                    'ref': move_ref,
                }
            )

            AccountMoveLine.with_context(check_move_validity=False).create(
                {
                    'name': _('Check Rejected'),
                    'account_id': check.deposit_bank_id.account_id.id,
                    'move_id': move_id.id,
                    'journal_id': journal.id,
                    'date': self.reject_date,
                    'debit': check.amount,
                    'credit': 0.0,
                    'ref': _(
                        'Rejected Check %(check_number)s on %(acc_number)s',
                        check_number=check.number,
                        acc_number=check.deposit_bank_id.acc_number,
                    ),
                }
            )
            AccountMoveLine.with_context(check_move_validity=False).create(
                {
                    'name': _('Check Rejected'),
                    'account_id': config.receivable_rejected_account_id.id,
                    'move_id': move_id.id,
                    'journal_id': journal.id,
                    'date': self.reject_date,
                    'debit': 0.0,
                    'credit': check.amount,
                    'ref': _('Rejected Check %s') % check.number,
                }
            )
            move_id._post()

            check.write(
                {
                    'issued_check_state': 'rejected',
                    'reject_move_id': move_id.id,
                    'reject_date': self.reject_date,
                }
            )
            check.message_post(
                body=_(
                    "Check Rejected. Reason: %(reason)s. ",
                    reason=self.reject_reason,
                )
            )

        return {'type': 'ir.actions.act_window_close'}


class RejectThirdPartyCheckWizard(models.TransientModel):
    _name = 'reject.third.party.check.wizard'
    _description = 'Reject third party check wizard'

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    reject_date = fields.Date('Reject date')
    reject_reason = fields.Text()

    def action_reject(self):
        """
        This method is called when the rejection is confirmed in the wizard.
        It change the state of the 3rd party check to 'rejected' and also creates a move.
        """
        check = self.env['account.check'].browse(self._context.get('active_id'))

        if check:
            AccountMoveLine = self.env['account.move.line']

            config = self.env['account.check.config'].search(
                [('company_id', '=', check.company_id.id)]
            )
            if not config:
                raise ValidationError(
                    _(
                        'ERROR! There is no check configuration for this Company!'
                    )
                )

            move_ref = _(
                'Reject Check %(check_number)s', check_number=check.number
            )

            move_id = self.env['account.move'].create(
                {
                    'journal_id': check.deposit_bank_id.journal_id.id,
                    'state': 'draft',
                    'date': self.reject_date,
                    'ref': move_ref,
                }
            )

            AccountMoveLine.with_context(check_move_validity=False).create(
                {
                    'name': _('Check Rejected'),
                    'account_id': config.rejected_account_id.id,
                    'move_id': move_id.id,
                    'journal_id': check.deposit_bank_id.journal_id.id,
                    'date': self.reject_date,
                    'debit': check.amount,
                    'credit': 0.0,
                    'ref': _(
                        'Rejected Check %(check_number)s on %(acc_number)s',
                        check_number=check.number,
                        acc_number=check.deposit_bank_id.acc_number,
                    ),
                }
            )
            AccountMoveLine.with_context(check_move_validity=False).create(
                {
                    'name': _('Check Rejected'),
                    'account_id': check.deposit_bank_id.account_id.id,
                    'move_id': move_id.id,
                    'journal_id': check.deposit_bank_id.journal_id.id,
                    'date': self.reject_date,
                    'debit': 0.0,
                    'credit': check.amount,
                    'ref': _('Rejected Check %s') % check.number,
                }
            )
            move_id._post()

            check.write(
                {
                    'third_party_check_state': 'rejected',
                    'reject_move_id': move_id.id,
                    'reject_date': self.reject_date,
                }
            )
            check.message_post(
                body=_(
                    "Check Rejected. Reason: %(reason)s. ",
                    reason=self.reject_reason,
                )
            )

        return {'type': 'ir.actions.act_window_close'}

    def get_account(self, config, check):
        """
        Return account based on check state

        Args:
            config (account.check.config): company check configuration
            check (account.third.party.check): 3rd party check

        Returns:
            account.account: Returns account object
        """
        account_id = False
        state = check.third_party_check_state
        if state == 'delivered':
            account_id = config.rejected_account_id.id
        elif state == 'deposited':
            account_id = check.deposit_bank_id.account_id.id
        elif state == 'in_wallet':
            account_id = config.account_id.id
        return account_id
