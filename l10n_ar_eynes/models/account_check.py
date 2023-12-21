import time

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class AccountCheckConfig(models.Model):
    _name = 'account.check.config'
    _description = 'Check Account Configuration'

    account_id = fields.Many2one(
        comodel_name='account.account',
        string='Main Check Account',
        required=True,
        help="In Argentina, Valores a Depositar is used, for example",
    )
    deferred_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Deferred Check Account',
        required=True,
    )
    deferred_journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Deferred Check Journal',
        required=True,
    )
    receivable_rejected_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Receivable Rejected Check Account',
        domain=[('internal_type', '=', 'receivable')],
        help="Partner's account in debit note generation.",
        required=True,
    )
    rejected_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Rejected Check Account',
        domain=[('internal_type', 'not in', ('receivable', 'payable'))],
        required=True,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.user.company_id.id,
    )

    def name_get(self):
        ret = []
        for config in self:
            ret.append(
                (
                    config.id,
                    "%s: %s" % (config.company_id.name, config.account_id.name),
                )
            )
        return ret


class AccountCheck(models.Model):
    _name = 'account.check'
    _description = 'Check'
    _rec_name = 'number'

    def _get_default_journal(self):
        if self._context.get('default_internal_type') == 'third_party':
            return self.env.ref('l10n_ar_eynes.third_party_checks_journal')
        return False

    number = fields.Char(string='Check Number', required=True, size=8)
    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Journal',
        required=True,
        default=_get_default_journal,
    )
    bank_id = fields.Many2one(comodel_name='res.bank', string='Bank')
    checkbook_format = fields.Selection(
        selection=[
            ('physical', 'Physical'),
            ('echeq', 'Echeq'),
        ],
        string='Format',
        required=True,
    )
    type = fields.Selection(
        selection=[('common', 'Common'), ('deferred', 'Deferred')],
        string='Type',
        default='common',
        required=True,
    )
    internal_type = fields.Selection(
        selection=[('issued', 'Issued'), ('third_party', 'Third Party')],
        string='Internal Type',
        default='third_party',
        required=True,
    )
    amount = fields.Float(string='Amount')
    issue_date = fields.Date(string='Issue Date')
    reject_date = fields.Date(string='Reject Date')
    payment_date = fields.Date(
        string='Payment Date', help="Only if this check is post dated"
    )
    crossed = fields.Boolean(string='Crossed')
    not_order = fields.Boolean(string='Not Order')
    clearing = fields.Selection(
        selection=[('24', '24 hs'), ('48', '48 hs'), ('72', '72 hs')],
        string='Clearing',
        default='24',
    )
    origin = fields.Char(string='Origin', size=64)
    signatory = fields.Char(string='Signatory', size=64)
    note = fields.Text(string="Note")
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        compute='_compute_currency',
        readonly=True,
        store=True,
    )
    currency_rate = fields.Float(
        digits=(12, 6),
        compute='_compute_currency_rate',
        readonly=True,
        store=True,
    )
    amount_currency = fields.Float(
        digits='Account',
        compute='_compute_amount_currency',
        string='Amount Currency',
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        readonly=True,
        default=lambda self: self.env.user.company_id.id,
    )

    @api.depends('amount', 'currency_rate')
    def _compute_amount_currency(self):
        for rec in self:
            try:
                rec.amount_currency = rec.amount / rec.currency_rate
            except ZeroDivisionError:
                rec.amount_currency = 0

    def unlink(self):
        """
        method gets overrided to ensure that check must be in specif state to get
        deleted
        """
        for check in self:
            if check.internal_type == 'third_party':
                if check.third_party_check_state != 'in_wallet':
                    raise UserError(
                        _(
                            "Check Error! You cannot delete a third check that is "
                            "not in Wallet"
                        )
                    )
            elif check.internal_type == 'issued':
                if check.issued_check_state != 'draft':
                    raise UserError(
                        _(
                            "Check Error! You cannot delete a check that is not in "
                            "Draft"
                        )
                    )
        return super(AccountCheck, self).unlink()

    def cancel_check(self, internal_type):
        """
        This method sets the checks state to 'cancelled'.

        Args:
            internal_type (selection): used to fiter 3rd party or issued

        Raises:
            UserError: Error coming from 3rd party check validation
            ValidationError: Error coming from issued check validation
        """
        if internal_type == 'third_party':
            state = 'third_party_check_state'
            for check in self.filtered(
                lambda rec: rec.internal_type == internal_type
            ):
                if check.third_party_check_state != 'in_wallet':
                    raise UserError(
                        _(
                            "Third Check Error! You cannot cancel check if it is "
                            "not in Wallet"
                        )
                    )
        elif internal_type == 'issued':
            state = 'issued_check_state'
            for check in self.filtered(
                lambda rec: rec.internal_type == internal_type
            ):
                if check.type == 'deferred' and check.accredited:
                    raise ValidationError(
                        _(
                            'Check number %s is postdated and has already been '
                            'accredited!\nPlease break the conciliation of that '
                            'check first.'
                        )
                        % check.number
                    )
        self.write({state: 'cancelled'})

    # ISSUED CHECK FIELDS AND METHODS
    issued_check_state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('waiting_accreditation', 'Waiting accreditation'),
            ('cancelled', 'Cancelled'),
            ('paid', 'Paid'),
            ('expired', 'Expired'),
            ('returned', 'Returned'),
            ('rejected', 'Rejected'),
            ('waiting_numeration', 'Waiting numeration'),
        ],
        default='draft',
        string='State',
    )
    checkbook_id = fields.Many2one(
        comodel_name='account.payment.method.line',
        string='Checkbook ID',
        ondelete='restrict',
        domain=[('payment_method_id.code', '=', 'check_printing')],
    )
    receiving_partner_id = fields.Many2one(
        comodel_name='res.partner', string='Receiving Entity'
    )
    payment_move_id = fields.Many2one(
        comodel_name='account.move', string='Payment Account Move'
    )
    payment_order_id = fields.Many2one(
        comodel_name='account.payment.order',
        string='Payment Order',
        ondelete='cascade',
    )
    clearance_move_id = fields.Many2one(
        comodel_name='account.move', string='Clearance Account Move'
    )
    accredited = fields.Boolean(
        string='Accredited', compute='_compute_accredit_state'
    )

    @api.depends('clearance_move_id')
    def _compute_accredit_state(self):
        for check in self:
            check.accredited = False
            if check.internal_type == 'issued':
                if check.clearance_move_id:
                    check.accredited = True
                else:
                    check.accredited = False

    def accredit_checks(self):
        """method for checks accreditation"""
        for check in self:
            if check.issued_check_state != "waiting_accreditation":
                raise ValidationError(
                    _("Check %s can't be accredited!") % self.number
                )

        for check in self:
            AccountCheckConfig = self.env['account.check.config']
            def_check_account = AccountCheckConfig.search(
                [('company_id', '=', self.env.user.company_id.id)]
            ).deferred_account_id
            def_check_journal = AccountCheckConfig.search(
                [('company_id', '=', self.env.user.company_id.id)]
            ).deferred_journal_id
            if not def_check_journal:
                raise UserError(
                    _(
                        "Error! There is no Journal configured for deferred checks."
                    )
                )

            current_date = time.strftime('%Y-%m-%d')

            AccountMoveLine = self.env['account.move.line']
            name_ref = 'Clearance Check ' + check.number
            move_vals = {
                'ref': name_ref,
                'journal_id': def_check_journal.id,
            }
            move_id = self.env['account.move'].create(move_vals)

            check.write({'clearance_move_id': move_id.id})

            # Creamos la línea contable que iguala el pago del cheque
            check_move_line_vals = {
                'journal_id': def_check_journal.id,
                'date': current_date,
                'name': name_ref,
                'account_id': def_check_account.id,
                'debit': check.amount,
                'move_id': move_id.id,
            }

            AccountMoveLine.with_context(check_move_validity=False).create(
                check_move_line_vals
            )

            if check.checkbook_id:
                # Creamos la línea contable que refiere
                # a la acreditación por parte del banco
                # solo si tiene referenciada una chequera (checkbook_id)
                bank_move_line_vals = {
                    'journal_id': def_check_journal.id,
                    'date': current_date,
                    'name': name_ref,
                    'account_id': self.checkbook_id.bank_account_id.account_id.id,
                    'credit': self.amount,
                    'move_id': move_id.id,
                }

                AccountMoveLine.with_context(check_move_validity=False).create(
                    bank_move_line_vals
                )

                # move_lines_to_reconcile = []
                # payment_move_line = move_line_obj.search([
                #     ('issued_check_id', '=', check.id)])
                # move_lines_to_reconcile.append(payment_move_line.id)
                # move_lines_to_reconcile.append(clearance_move_line.id)
                # reconcile_recordset = move_line_obj.browse(move_lines_to_reconcile)
                # reconcile_recordset.reconcile()

        return self.write({"issued_check_state": "issued"})

    def break_conciliation(self):
        for check in self.filtered(lambda rec: rec.internal_type == 'issued'):
            if check.issued_check_state != "issued":
                raise ValidationError(
                    _("Can't break conciliation of a not issued check!")
                )
            if not check.accredited:
                raise ValidationError(
                    _("Can't break conciliation of a not accredited check!")
                )
        for check in self.filtered(lambda rec: rec.internal_type == 'issued'):
            move = check.clearance_move_id
            move.line_ids.remove_move_reconcile()
            move.button_cancel()
            move.unlink()
            check.write({'issued_check_state': 'waiting_accreditation'})

    @api.model
    def issued_create_voucher_move_line(self):
        voucher = self.payment_order_id

        # Buscamos la cuenta contable para el asiento del cheque
        # Esta cuenta se corresponde con la cuenta de banco de donde
        # pertenece el cheque
        if self.type == 'deferred':
            # Buscamos la configuracion de cheques
            check_config_obj = self.env['account.check.config']
            config = check_config_obj.search(
                [('company_id', '=', voucher.company_id.id)]
            )
            if not len(config):
                raise ValidationError(
                    _('There is no check configuration for this Company!')
                )

            account_id = config.deferred_account_id.id
            date_maturity = self.payment_date
        else:
            account_id = self.journal_id.bank_account_id.account_id.id
            date_maturity = voucher.date_due

        if not account_id:
            raise UserError(
                _(
                    "Error! Bank Account has no account "
                    "configured. Please, configure an "
                    "account for the bank account used for checks!"
                )
            )

        # TODO: Chequear que funcione bien en
        # multicurrency estas dos lineas de abajo
        company_currency = voucher.company_id.currency_id.id
        current_currency = self.currency_id.id
        check_currency = self.checkbook_id.bank_account_id.currency_id.id
        if check_currency != company_currency:
            amount_in_company_currency = (
                voucher._convert_paid_amount_in_company_currency(self.amount)
            )
        else:
            amount_in_company_currency = self.amount
        debit = credit = 0.0
        if voucher.type in ('purchase', 'payment'):
            credit = amount_in_company_currency
        elif voucher.type in ('sale', 'receipt'):
            debit = amount_in_company_currency
        if debit < 0:
            credit = -debit
            debit = 0.0
        if credit < 0:
            debit = -credit
            credit = 0.0
        sign = debit - credit < 0 and -1 or 1

        # Creamos la linea contable perteneciente al cheque
        if self.number:
            reference = _('Issued Check %s') % (self.number or '/')
        else:
            reference = _('Checkbook Number %s') % (
                self.checkbook_id.name or '/'
            )

        move_line = {
            'name': reference,
            'debit': debit,
            'credit': credit,
            'account_id': account_id,
            'journal_id': voucher.journal_id.id,
            'partner_id': voucher.partner_id.id,
            'currency_id': company_currency != current_currency
            and current_currency
            or False,
            'amount_currency': company_currency != current_currency
            and sign * self.amount_currency
            or 0.0,
            'date': voucher.date,
            'date_maturity': date_maturity,
        }
        return move_line

    # THIRD PARTY CHECK FIELDS AND METHODS
    third_party_check_state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('in_wallet', 'In wallet'),
            ('deposited', 'Deposited'),
            ('delivered', 'Delivered'),
            ('cancelled', 'Cancelled'),
            ('rejected', 'Rejected'),
            ('returned', 'Returned'),
        ],
        default='draft',
        string='State',
    )
    deposit_bank_id = fields.Many2one(
        comodel_name='res.partner.bank', string='Deposit Account'
    )
    source_payment_order_id = fields.Many2one(
        comodel_name='account.payment.order',
        string='Source Payment Order',
        ondelete="cascade",
        readonly=True,
    )
    debit_note_id = fields.Many2one(
        comodel_name='account.move',
        string='Debit Note',
        readonly=True,
        help="In case of rejection of the third check",
    )
    source_partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Source Partner',
        required=False,
        readonly=True,
    )
    destiny_partner_id = fields.Many2one(
        comodel_name='res.partner', string='Destiny Partner'
    )
    deposit_move_id = fields.Many2one(
        comodel_name='account.move', string='Deposit Move', readonly=True
    )
    deposit_journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Deposit Journal',
        readonly=True,
        compute='_compute_deposit_journal_id',
    )
    bank_branch = fields.Char(string='Bank Branch', size=64)
    zip = fields.Char(string='Zip Code', size=64)
    reception_date = fields.Date(string='Reception Date')
    endorsement_date = fields.Date(string='Endorsement Date')
    deposit_date = fields.Date(string='Deposit Date', readonly=True)
    signatory_vat = fields.Char(string='Signatory VAT', size=64)
    signatory_account = fields.Char(string='Signatory account', size=64)
    deposit_slip = fields.Char(string='Deposit Slip', size=64)
    dest = fields.Char(string='Destiny', size=64)

    @api.depends('deposit_move_id')
    def _compute_deposit_journal_id(self):
        for check in self.filtered(
            lambda rec: rec.internal_type == 'third_party'
        ):
            if check.deposit_move_id:
                check.deposit_journal_id = check.deposit_move_id.journal_id
            else:
                check.deposit_journal_id = False

    @api.onchange('number')
    def _onchange_number(self):
        if not self.number:
            return
        if not self.number.isnumeric():
            raise ValidationError(
                _('Check Number must not have non numerical characters')
            )
        self.number = self.number.zfill(8)

    def to_wallet(self):
        # Funcion llamada al validar un pago de cliente que contenga cheques
        for check in self.filtered(
            lambda rec: rec.internal_type == 'third_party'
        ):
            voucher = check.source_payment_order_id
            if not voucher:
                raise UserError(
                    _(
                        'Check Error! Check has to '
                        'be associated with a voucher'
                    )
                )

            partner_id = voucher.partner_id.id
            vals = {}
            if voucher.type == 'receipt':
                vals['source_partner_id'] = partner_id

            if not check.origin:
                vals['origin'] = voucher.reference
            vals['third_party_check_state'] = 'in_wallet'

            # Si es cheque comun tomamos la fecha de emision
            # como feche de pago tambien porque seria un cheque al dia
            if check.type == 'common':
                vals['payment_date'] = check.issue_date

            check.write(vals)
        return True

    def check_to_wallet(self):
        if self.deposit_move_id:
            self.deposit_move_id.button_cancel()
            self.deposit_move_id.with_context(force_delete=True).unlink()
            self.write({'third_party_check_state': 'in_wallet'})
        else:
            raise ValidationError(
                _(
                    'There is no reference for account move. '
                    'Imposible to go back to wallet.'
                )
            )

    def return_wallet(self):
        # Todos los cheques tienen que estar en delivered
        for check in self.filtered(
            lambda rec: rec.internal_type == 'third_party'
        ):
            if check.third_party_check_state != 'delivered':
                raise UserError(
                    _(
                        "Third Check Error! You cannot return to "
                        "wallet a check if it is not in Delivered state"
                    )
                )
        self.write(
            {
                'third_party_check_state': 'in_wallet',
                'endorsement_date': False,
                'destiny_partner_id': False,
                'dest': '',
            }
        )
        return True

    def check_delivered(self):
        # Transicion efectuada al validar un pago a proveedores que entregue
        # cheques de terceros
        PaymentOrder = self.env['account.payment.order']
        vals = {'third_party_check_state': 'delivered'}
        for check in self:
            po = PaymentOrder.search(
                [
                    ('third_party_check_ids', '=', check.id),
                    ('state', '!=', 'cancel'),
                ]
            )

            if len(po) > 1:
                raise UserError(
                    _('There are more than one voucher referenced to check %s.')
                    % check.number
                )
            if not check.endorsement_date:
                vals['endorsement_date'] = po.date or time.strftime('%Y-%m-%d')
            vals['destiny_partner_id'] = po.partner_id.id

            if not check.dest:
                vals['dest'] = po.reference

            check.write(vals)
        return True

    @api.model
    def third_party_create_voucher_move_line(self, voucher):
        check_config_obj = self.env['account.check.config']

        # Buscamos la configuracion de cheques
        config = check_config_obj.search(
            [('company_id', '=', voucher.company_id.id)]
        )
        if not len(config):
            raise UserError(
                _('ERROR! There is no check configuration for this Company!')
            )

        # TODO: Chequear que funcione bien en
        # multicurrency estas dos lineas de abajo
        company_currency = voucher.company_id.currency_id.id
        current_currency = self.currency_id.id

        # amount_in_company_currency = (
        #     voucher._convert_paid_amount_in_company_currency(self.amount)
        # )
        amount_in_company_currency = self.amount

        debit = credit = 0.0
        if voucher.type in ('purchase', 'payment'):
            credit = amount_in_company_currency
        elif voucher.type in ('sale', 'receipt'):
            debit = amount_in_company_currency
        if debit < 0:
            credit = -debit
            debit = 0.0
        if credit < 0:
            debit = -credit
            credit = 0.0
        sign = debit - credit < 0 and -1 or 1

        # Creamos la linea contable perteneciente al cheque
        move_line = {
            'name': _('Third Check ') + self.number or '/',
            'debit': debit,
            'credit': credit,
            'account_id': config.account_id.id,
            'journal_id': voucher.journal_id.id,
            'partner_id': voucher.partner_id.id,
            'currency_id': company_currency != current_currency
            and current_currency
            or False,
            'amount_currency': company_currency != current_currency
            and sign * self.amount_currency
            or 0.0,
            'date': voucher.date,
            'date_maturity': self.payment_date or self.issue_date,
        }

        return move_line

    @api.depends(
        'payment_order_id.currency_id', 'source_payment_order_id.currency_id'
    )
    def _compute_currency(self):
        for rec in self:
            if rec.internal_type == 'issued':
                rec.currency_id = rec.payment_order_id.currency_id
            else:
                rec.currency_id = rec.source_payment_order_id.currency_id

    @api.depends(
        'payment_order_id.payment_rate', 'source_payment_order_id.payment_rate'
    )
    def _compute_currency_rate(self):
        for rec in self:
            if rec.internal_type == 'issued':
                rec.currency_rate = rec.payment_order_id.payment_rate
            else:
                rec.currency_rate = rec.source_payment_order_id.payment_rate

    _sql_constraints = [
        (
            "unique_record",
            "unique(number, checkbook_id, journal_id, checkbook_format)",
            _("This record already exists"),
        ),
    ]
