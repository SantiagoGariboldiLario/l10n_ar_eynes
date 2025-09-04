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

    def _get_field_string(self, obj, name):
        return (
            self.env['ir.model.fields']
            .search([('name', '=', name), ('model', '=', obj._name)])
            .field_description
        )

    def _missing_config_fields_for_delivered_third_party_check(self, config):
        missing_fields = []
        if not config.receivable_rejected_account_id:
            missing_fields.append(
                self._get_field_string(config, 'receivable_rejected_account_id')
                + ' (receivable_rejected_account_id)'
            )
        if not config.rejected_account_id:
            missing_fields.append(
                self._get_field_string(config, 'rejected_account_id')
                + ' (rejected_account_id)'
            )

        return missing_fields

    def _create_account_move_line(self, check, config, params):
        AccountMoveLine = self.env['account.move.line']

        move_id = self.env['account.move'].create(
            {
                'journal_id': params['move_journal_id'],
                'state': 'draft',
                'date': self.reject_date,
                'ref': params['move_ref'],
            }
        )

        AccountMoveLine.with_context(check_move_validity=False).create(
            {
                'name': _('Check Rejected'),
                'account_id': params['move_line_debit_account_id'],
                'move_id': move_id.id,
                'journal_id': params['move_journal_id'],
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
                'account_id': params['move_line_credit_account_id'],
                'move_id': move_id.id,
                'journal_id': params['move_journal_id'],
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

    def action_reject(self):
        """
        This method is called when the rejection is confirmed in the wizard.
        It change the state of the 3rd party check to 'rejected' and also creates a move.
        """
        check = self.env['account.check'].browse(self._context.get('active_id'))

        if check:
            config = self.env['account.check.config'].search(
                [('company_id', '=', check.company_id.id)]
            )
            if not config:
                raise ValidationError(
                    _(
                        'ERROR! There is no check configuration for this Company!'
                    )
                )

            if check.third_party_check_state not in (
                'in_wallet',
                'delivered',
                'deposited',
            ):
                raise UserError(
                    _(
                        'ERROR! This check is not Delivered, Deposited or In Wallet!'
                    )
                )

            missing_fields = (
                self._missing_config_fields_for_delivered_third_party_check(
                    config
                )
            )
            if missing_fields:
                raise ValidationError(
                    _(
                        'Missing config params for check. Go to Configuration/Check configuration and'
                        ' complete the following fields for company %(company)s: \n\n\t* %(fields)s',
                        company=check.company_id.name,
                        fields='\n\t* '.join(missing_fields),
                    )
                )

            params = {
                'move_ref': _(
                    'Reject Check %(check_number)s', check_number=check.number
                ),
                'move_journal_id': config.rejected_issued_checks_journal_id.id,
                'move_line_credit_account_id': self.get_account(config, check),
                'move_line_debit_account_id': config.rejected_account_id.id,
            }
            self._create_account_move_line(check, config, params)

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
            account_id = config.receivable_rejected_account_id.id
        elif state == 'deposited':
            account_id = check.deposit_bank_id.journal_id.suspense_account_id.id
        elif state == 'in_wallet':
            account_id = config.account_id.id
        return account_id
