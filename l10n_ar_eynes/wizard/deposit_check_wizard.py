import time

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class DepositCheckwizard(models.TransientModel):
    _name = 'deposit.check.wizard'
    _description = 'Deposit check wizard'

    voucher_number = fields.Char(string='Voucher Number', size=32)
    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Depositing Bank',
        required=True,
        domain=[('type', 'in', ('cash', 'bank'))],
        default=lambda self: self._get_journal(),
    )
    bank_account_id = fields.Many2one(
        comodel_name='res.partner.bank',
        string='Depositing Bank Account',
        required=True,
        default=lambda self: self._get_bank_account(),
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
        default=lambda self: self.env.user.company_id.id,
    )

    def _get_journal(self):
        journal_id = False
        voucher_obj = self.env['account.payment.order']
        model = self._context.get('active_model', False)
        if model and model == 'account.check':
            ids = self.env.context.get('active_ids', [])
            checks = self.env[model].browse(ids)
            check_type = checks.mapped('internal_type')
            if len(check_type) > 1:
                raise UserError(
                    _(
                        "You are trying to deposit issued checks an third party checks at the same time."
                    )
                )
            if check_type[0] == 'third_party':
                vouchers = checks.read(['source_payment_order_id'])
                if (
                    vouchers
                    and vouchers[0]
                    and 'source_payment_order_id' in vouchers[0]
                ):
                    if vouchers[0]['source_payment_order_id']:
                        payment_order_id = vouchers[0][
                            'source_payment_order_id'
                        ][0]
                        journal_id = voucher_obj.browse(payment_order_id).read(
                            ['journal_id']
                        )[0]['journal_id'][0]
            else:
                journals = checks.mapped('journal_id')
                if len(journals) > 1:
                    raise UserError(
                        _(
                            "You are trying to deposit issued checks from different banks at the same time."
                        )
                    )
                journal_id = journals[0]

        return journal_id

    def _get_bank_account(self):
        bank_account = False
        model = self._context.get('active_model', False)
        if model and model == 'account.check':
            ids = self.env.context.get('active_ids', [])
            checks = self.env[model].browse(ids)
            check_type = checks.mapped('internal_type')
            if len(check_type) > 1:
                raise UserError(
                    _(
                        "You are trying to deposit issued checks an third party checks at the same time."
                    )
                )
            if check_type[0] == 'issued':
                journals = checks.mapped('journal_id')
                if len(journals) > 1:
                    raise UserError(
                        _(
                            "You are trying to deposit issued checks from different banks at the same time."
                        )
                    )
                bank_account = journals[0].bank_account_id
        return bank_account

    def view_init(self, fields_list):
        """
        This method gets overrided to ensure that the check's
        internal type is third_party and its state is 'in_wallet'
        """
        check = self.env['account.check'].browse(
            self.env.context.get('active_id', False)
        )
        if check:
            if check.internal_type == 'third_party':
                if check.third_party_check_state != 'in_wallet':
                    raise UserError(
                        _(
                            "Error! The selected checks must be in wallet.\n"
                            "Check %s is not in wallet"
                        )
                        % (check.number)
                    )
            else:
                if check.issued_check_state != 'waiting_accreditation':
                    raise UserError(
                        _(
                            "Error! The selected checks must be in Waiting accreditation.\n"
                            "Check %s is not in Waiting accreditation"
                        )
                        % (check.number)
                    )

        else:
            raise ValidationError(_("Error when searching for the check"))

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

    @api.onchange('bank_account_id')
    def onchange_bank_account(self):
        if not self.bank_account_id:
            return
        if self.bank_account_id.journal_id:
            self.journal_id = self.bank_account_id.journal_id.id

    def _check_validations(self, checks, deposit_date):
        third_party = checks.filtered(
            lambda check: check.internal_type == 'third_party'
        )
        # Filter checks that are third-party and not in wallet
        third_party_not_in_wallet = third_party.filtered(
            lambda check: check.third_party_check_state != 'in_wallet'
        )
        if third_party_not_in_wallet:
            raise UserError(
                _(
                    "Error! The selected checks must be in wallet. Checks with issues: %s"
                )
                % ', '.join(check.number for check in third_party_not_in_wallet)
            )

        # Check conditions for third-party checks in wallet and deferred issued checks
        error_checks = third_party.filtered(
            lambda check: not check.payment_date
            or check.payment_date > deposit_date
        ) + checks.filtered(
            lambda check: check.type == 'deferred'
            and (not check.payment_date or check.payment_date > deposit_date)
        )
        if error_checks:
            raise UserError(
                _(
                    "Cannot deposit! You cannot deposit the selected checks. Payment Date is not defined or"
                    " exceeds Deposit Date. Checks with issues: %s"
                )
                % ', '.join(check.number for check in error_checks)
            )

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

        checks = self.env['account.check'].browse(
            self.env.context.get('active_ids', [])
        )

        if checks:
            self._check_validations(checks, deposit_date)

            account_check_id = self._get_source_account_check(
                self.company_id.id
            )

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
                        'journal_id': self.journal_id.id,
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
                debit_account = (
                    self.bank_account_id.account_id.id
                    if check.internal_type == 'issued'
                    else check_config.deferred_account_id.id
                )
                credit_account = (
                    account_check_id
                    if check.internal_type == 'issued'
                    else self.bank_account_id.account_id.id
                )
                AccountMoveLine.with_context(check_move_validity=False).create(
                    {
                        'name': _('Check Deposit'),
                        # 'centralisation': 'normal',
                        'account_id': debit_account,
                        'move_id': move_id.id,
                        'journal_id': self.journal_id.id,
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
                        'account_id': credit_account,
                        'move_id': move_id.id,
                        'journal_id': self.journal_id.id,
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
                else:
                    check.write(
                        {
                            'issued_check_state': 'paid',
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
