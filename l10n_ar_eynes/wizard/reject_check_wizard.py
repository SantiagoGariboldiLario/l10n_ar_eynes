from odoo import _, fields, models
from odoo.exceptions import ValidationError


class RejectIssuedCheckWizard(models.TransientModel):
    _name = 'reject.issued.check.wizard'
    _description = 'Reject issued check wizard'

    reject_date = fields.Date(string='Reject date')
    note = fields.Text(string='Note')
    reason_id = fields.Many2one(
        comodel_name='reason.rejected.check',
        domain="[('type', '=', 'rejected')]",
        string='Reason',
    )
    generate_rejection_journal_entry = fields.Boolean(
        string='Generate Rejection Journal Entry', default=True
    )  # Este campo queda deprecado a partir del 9/5/24, aparentemente SIEMPRE se genera el asiento

    def action_reject(self):
        """action that rejects the issued check"""
        check = self.env['account.check'].browse(
            self.env.context.get('active_id', False)
        )
        if check:
            check.write({'reject_date': self.reject_date, 'note': self.note})
            if self.generate_rejection_journal_entry:
                self.create_rejected_journal_entry(check)
            check.write({'issued_check_state': 'rejected'})
        return {'type': 'ir.actions.act_window_close'}

    def create_rejected_journal_entry(self, check):
        """
        This method generates an invoice which register the
        check rejection as an invoice movement. It also adds the lines to the payment order

        Args:
            check (account.issued.check): check record
        """
        AccoutMoveLine = self.env['account.move.line']

        payment = check.payment_order_id
        journal = self.env.user.company_id.rejected_issued_checks_journal_id
        if not journal:
            raise ValidationError(
                _("No journal configured for rejected checks")
            )

        def_check_account = (
            self.env['account.check.config']
            .search([('company_id', '=', self.env.user.company_id.id)])
            .deferred_account_id.id
        )
        if not def_check_account:
            raise ValidationError(_("No Deferred account id configured"))

        ctx = {
            'date': self.reject_date,
            'check_move_validity': False,
        }

        for payment_line in payment.move_line_ids:
            if payment_line.issued_check_id == check:
                original_move_data = payment.account_move_get()
                original_move_data['journal_id'] = journal.id
                original_move_data['state'] = 'draft'
                move = (
                    self.env['account.move']
                    .with_context(**ctx)
                    .create(original_move_data)
                )

                # Get the name of the account_move just created
                counterpart_account = (
                    self.env['account.account']
                    .search([('code', '=', payment_line.counterpart)])
                    .id
                )
                if not counterpart_account:
                    raise ValidationError(_("No counterpart account found"))
                inverse_supplier_line = {
                    'name': '/',
                    'account_id': counterpart_account,
                    'move_id': move.id,
                    'partner_id': payment_line.partner_id.id,
                    'date': self.reject_date,
                    'credit': payment_line.credit,
                    'debit': 0,
                    'amount_currency': payment_line.amount_currency,
                    'journal_id': original_move_data['journal_id'],
                    'currency_id': payment_line.currency_id.id,
                    'analytic_account_id': payment_line.analytic_account_id.id,
                    'ref': _('Rejected check')
                    + ': '
                    + (payment_line.name or '/'),
                }
                AccoutMoveLine.with_context(**ctx).create(inverse_supplier_line)

                inverse_check_line = {
                    'name': _('Rejected check')
                    + ': '
                    + (payment_line.name or '/'),
                    'account_id': def_check_account,
                    'move_id': move.id,
                    'partner_id': payment_line.partner_id.id,
                    'date': self.reject_date,
                    'credit': 0,
                    'debit': payment_line.credit,
                    'amount_currency': payment_line.amount_currency,
                    'journal_id': original_move_data['journal_id'],
                    'currency_id': payment_line.currency_id.id,
                    'analytic_account_id': payment_line.analytic_account_id.id,
                    'ref': _('Rejected check')
                    + ': '
                    + (payment_line.name or '/'),
                }
                AccoutMoveLine.with_context(**ctx).create(inverse_check_line)
                move.post()


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
            check.reject_date = self.reject_date

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
