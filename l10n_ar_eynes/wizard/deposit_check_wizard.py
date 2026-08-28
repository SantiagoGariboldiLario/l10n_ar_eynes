import time

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class DepositCheckwizard(models.TransientModel):
    _name = 'deposit.check.wizard'
    _description = 'Deposit check wizard'

    voucher_number = fields.Char(string='Voucher Number', size=32)
    bank_account_id = fields.Many2one(
        comodel_name='res.partner.bank',
        string='Depositing Bank Account',
        required=True,
        domain=lambda self: [
            ('partner_id', '=', self.env.company.partner_id.id),
        ],
    )
    date = fields.Date(
        string='Deposit Date',
        required=True,
        default=lambda *a: time.strftime('%Y-%m-%d'),
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company.id,
    )
    third_party_checks = fields.Many2many(
        comodel_name='account.check',
        string='Checks to Deposit',
        default=lambda self: self._get_default_checks(),
    )
    third_party_check_id = fields.Many2one(
        comodel_name='account.check',
        string='Check',
        default=lambda self: self._get_third_party_check_id(),
        readonly=True,
    )
    multichecks = fields.Boolean(
        default=lambda self: self._get_default_method()
    )

    @api.model
    def _get_context_check_ids(self):
        """Get the checks selected by the user, either from a list
        selection (active_ids) or from a single record (active_id)"""
        check_ids = self.env.context.get('active_ids') or []
        if not check_ids:
            active_id = self.env.context.get('active_id')
            check_ids = [active_id] if active_id else []
        return check_ids

    @api.model
    def _get_default_checks(self):
        return [(6, False, self._get_context_check_ids())]

    @api.model
    def _get_third_party_check_id(self):
        check_ids = self._get_context_check_ids()
        return check_ids[0] if check_ids else False

    @api.model
    def _get_default_method(self):
        return not self.env.context.get('one_check', False)

    @api.model
    def default_get(self, fields_list):
        """Validate the preselected checks before showing the wizard, so the
        user does not fill it in to get an error afterwards.

        The wizard may also be opened with no selection at all, from the
        always visible button of the check list. In that case it opens empty
        and the user picks the checks inside it.
        """
        res = super().default_get(fields_list)
        checks = self.env['account.check'].browse(self._get_context_check_ids())
        if checks:
            self._check_deposit_allowed(checks)
        return res

    @api.model
    def _check_deposit_allowed(self, checks):
        """Only third party checks in wallet can be deposited"""
        issued = checks.filtered(
            lambda check: check.internal_type != 'third_party'
        )
        if issued:
            raise UserError(_("You can't do this operation for issued checks."))

        not_in_wallet = checks.filtered(
            lambda check: check.third_party_check_state != 'in_wallet'
        )
        if not_in_wallet:
            raise UserError(
                _(
                    "Error! The selected checks must be in wallet. Checks with issues: %s"
                )
                % ', '.join(check.number for check in not_in_wallet)
            )

    # TODO: Esto deberiamos obtenerlo del anterior asiento contable. Tenemos
    # que guardar una referencia a los asientos contables de los cheques.
    # Por ahora, la cuenta contable de donde sacar el cheque la obtenemos de
    # la configuracion por compania

    def _get_source_account_check(self, company_id):
        # Obtenemos la configuracion
        res = self.env['account.check.config'].search(
            [('company_id', '=', company_id)]
        )
        if not res:
            raise UserError(
                _('Error! There is no check configuration for this Company!')
            )
        src_account = res.read(['account_id'])[0]
        if 'account_id' in src_account:
            return src_account['account_id'][0]

        raise UserError(
            _('Error! Bad Treasury configuration for this Company!')
        )

    def _check_validations(self, checks, deposit_date):
        self._check_deposit_allowed(checks)

        # Check conditions for third-party checks in wallet and deferred issued checks
        error_checks = checks.filtered(
            lambda check: not check.payment_date
            or (check.issue_date and check.issue_date > deposit_date)
        )
        if error_checks:
            raise UserError(
                _(
                    "Cannot deposit! You cannot deposit the selected checks. Payment Date is not defined or"
                    " exceeds Deposit Date. Checks with issues: %s"
                )
                % ', '.join(check.number for check in error_checks)
            )

    def _get_checks_to_deposit(self):
        """Checks the wizard is going to operate on"""
        if self.multichecks:
            return self.third_party_checks
        return self.third_party_check_id

    def action_deposit(self):
        AccountMoveLine = self.env['account.move.line']

        deposit_date = self.date or time.strftime('%Y-%m-%d')

        if not self.bank_account_id.account_id:
            raise UserError(
                _(
                    "Error! You have to configure an account on "
                    "Bank Account %(bank_name)s: %(acc_number)s",
                    bank_name=self.bank_account_id.bank_name,
                    acc_number=self.bank_account_id.acc_number,
                )
            )

        checks = self._get_checks_to_deposit()
        if not checks:
            raise UserError(_("You must select at least one check."))

        self._check_validations(checks, deposit_date)

        account_check_id = self._get_source_account_check(self.company_id.id)

        # name = self.pool.get('ir.sequence').get_id(cr, uid,
        # check.payment_order_id.journal_id.id)

        for check in checks:
            move_ref = _(
                'Deposit Check %(check_number)s', check_number=check.number
            )
            if self.voucher_number:
                move_ref += _(
                    ' [%(voucher_number)s]',
                    voucher_number=self.voucher_number,
                )

            move_id = self.env['account.move'].create(
                {
                    'name': '/',
                    'journal_id': self.bank_account_id.journal_id.id,
                    'state': 'draft',
                    'date': deposit_date,
                    'ref': move_ref,
                }
            )
            check_config = self.env['account.check.config'].search(
                [('deferred_account_id', '!=', False)], limit=1
            )
            if not check_config:
                raise UserError(
                    _(
                        "There is not check configuration. You need to set an account to do this operation."
                    )
                )

            AccountMoveLine.with_context(check_move_validity=False).create(
                {
                    'name': _('Check Deposit'),
                    # 'centralisation': 'normal',
                    'account_id': self.bank_account_id.journal_id.suspense_account_id.id,
                    'move_id': move_id.id,
                    'journal_id': self.bank_account_id.journal_id.id,
                    'date': deposit_date,
                    'debit': check.amount,
                    'credit': 0.0,
                    'ref': _(
                        'Deposit Check %(check_number)s on %(acc_number)s',
                        check_number=check.number,
                        acc_number=self.bank_account_id.acc_number,
                    ),
                }
            )
            AccountMoveLine.with_context(check_move_validity=False).create(
                {
                    'name': _('Check Deposit'),
                    # 'centralisation': 'normal',
                    'account_id': account_check_id,
                    'move_id': move_id.id,
                    'journal_id': self.bank_account_id.journal_id.id,
                    'date': deposit_date,
                    'debit': 0.0,
                    'credit': check.amount,
                    'ref': _('Deposit Check %s') % check.number,
                }
            )
            if check.internal_type == 'third_party':
                check.write(
                    {
                        'third_party_check_state': 'deposited',
                        'deposit_bank_id': self.bank_account_id.id,
                        'deposit_date': deposit_date,
                        'deposit_slip': self.voucher_number,
                        'deposit_move_id': move_id.id,
                    }
                )

            # Se postea el asiento llamando a la funcion post de account_move.
            # TODO: Se podria poner un check en el wizard
            # para que elijan si postear el asiento o no.
            move_id._post()

        return {'type': 'ir.actions.act_window_close'}
