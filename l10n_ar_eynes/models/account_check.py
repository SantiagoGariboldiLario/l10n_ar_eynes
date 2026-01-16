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
        help="Partner's account in debit note generation.",
        required=True,
    )
    rejected_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Rejected Check Account',
        required=True,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company.id,
    )
    expired_issued_checks_account_id = fields.Many2one(
        comodel_name='account.account',
        required=True,
    )
    rejected_issued_checks_journal_id = fields.Many2one(
        comodel_name='account.journal',
        readonly=False,
        domain="[('company_id', '=', company_id)]",
        string='Rejected issued checks journal',
    )
    rejected_check_product_id = fields.Many2one(
        comodel_name='product.product',
        readonly=False,
        string='Rejected check Product ID',
        help='Product to be use on Debit Note when a Third Party check is rejected',
    )
    display_name = fields.Char(compute='_compute_display_name', store=True)

    @api.depends('company_id.name', 'account_id.name')
    def _compute_display_name(self):
        for config in self:
            config.display_name = "%s: %s" % (
                config.company_id.name,
                config.account_id.name,
            )


class AccountCheck(models.Model):
    _name = 'account.check'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Check'
    _rec_name = 'number'

    def _get_default_journal(self):
        if self._context.get('default_internal_type') == 'third_party':
            return self.env['account.journal'].search(
                [('type', '=', 'third_party_checks')]
            )
        return False

    number = fields.Char(string='Check Number', required=True, size=8)
    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Journal',
        required=True,
        default=lambda self: self._get_default_journal(),
    )
    journal_bank_id = fields.Many2one(
        related='journal_id.bank_account_id', string="Journal Bank Account"
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
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        compute='_compute_currency',
        store=True,
    )
    currency_rate = fields.Float(
        digits=(12, 6),
        compute='_compute_currency_rate',
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
        default=lambda self: self.env.company.id,
    )
    reject_date = fields.Date(string='Reject Date')
    reject_move_id = fields.Many2one(
        comodel_name='account.move', string='Reject Account Move'
    )
    cancel_date = fields.Date(string='Cancelation Date')
    cancel_move_id = fields.Many2one(
        comodel_name='account.move', string='Cancelation Account Move'
    )
    expired_date = fields.Date(string='Expiration Date')
    expired_move_id = fields.Many2one(
        comodel_name='account.move', string='Expiration Account Move'
    )

    @api.depends(
        'payment_order_id.currency_id', 'source_payment_order_id.currency_id'
    )
    def _compute_currency(self):
        for rec in self:
            currency_id = rec.currency_id
            if rec.internal_type == 'issued' and rec.payment_order_id:
                currency_id = rec.payment_order_id.currency_id
            elif (
                rec.internal_type == 'third_party'
                and rec.source_payment_order_id
            ):
                currency_id = rec.source_payment_order_id.currency_id
            rec.currency_id = currency_id

    @api.depends(
        'payment_order_id.payment_rate', 'source_payment_order_id.payment_rate'
    )
    def _compute_currency_rate(self):
        for rec in self:
            if rec.internal_type == 'issued':
                rec.currency_rate = rec.payment_order_id.payment_rate
            else:
                rec.currency_rate = rec.source_payment_order_id.payment_rate

    @api.depends('amount', 'currency_rate')
    def _compute_amount_currency(self):
        for rec in self:
            try:
                rec.amount_currency = rec.amount / rec.currency_rate
            except ZeroDivisionError:
                rec.amount_currency = 0

    @api.model_create_multi
    def create(self, vals_list):
        """
        Override create method to ensure that checks have a currency and a company set --> Prevent Error
        when checks are imported.
        """
        for val in vals_list:
            if self.env.context.get('import_file', False):
                if not val.get('currency_rate', False):
                    val['currency_rate'] = 1.0
                if not val.get('currency_id', False):
                    val['currency_id'] = self.env.company.currency_id.id
            if not val.get('company_id', False):
                # No lo solicitaron pero para mi tiene que agregarse esta validación
                val['company_id'] = self.env.company.id
        return super().create(vals_list)

    def unlink(self):
        """
        Unlink checks was moved to api.ondelete method
        """
        return super().unlink()

    @api.ondelete(at_uninstall=False)
    def _check_unlink_constraints(self):
        undeletable_third_party = self.filtered(
            lambda c: c.internal_type == 'third_party'
            and c.third_party_check_state != 'draft'
        )
        if undeletable_third_party:
            raise UserError(
                _(
                    "Check Error! You cannot delete a third check that is not in Draft"
                )
            )

        issued_checks = self.filtered(lambda c: c.internal_type == 'issued')
        if issued_checks:
            raise UserError(_("Check Error! You cannot delete an Issued Check"))

    def cancel_check(self, reason):
        """
        This method sets the checks state to 'cancelled'.

        Raises:
            UserError: Error coming from 3rd party check validation
            ValidationError: Error coming from issued check validation
        """
        AccountCheckConfig = self.env['account.check.config']
        AccountMoveLine = self.env['account.move.line']
        third_party_checks = self.filtered(
            lambda check: check.internal_type == 'third_party'
        )
        issued_checks = self.filtered(
            lambda check: check.internal_type == 'issued'
        )
        if third_party_checks:
            for check in third_party_checks:
                if check.third_party_check_state == 'deposited':
                    raise UserError(
                        _(
                            "Third Check Error! You cannot cancel check if it is deposited."
                        )
                    )
            rej_check_account = AccountCheckConfig.search(
                [('company_id', '=', self.env.company.id)]
            ).rejected_account_id
            if not rej_check_account:
                raise UserError(
                    _(
                        "Error! There is no Account configured for rejected third checks."
                    )
                )
            check_account = AccountCheckConfig.search(
                [('company_id', '=', self.env.company.id)]
            ).account_id
            if not check_account:
                raise UserError(
                    _("Error! There is no Account configured for third checks.")
                )
            def_check_journal = AccountCheckConfig.search(
                [('company_id', '=', self.env.company.id)]
            ).deferred_journal_id
            if not def_check_journal:
                raise UserError(
                    _(
                        "Error! There is no Journal configured for deferred checks."
                    )
                )
            for check in third_party_checks:
                name_ref = 'Cancel Check ' + check.number
                move_vals = {
                    'ref': name_ref,
                    'journal_id': def_check_journal.id,
                    # 'date': date,
                }
                move_id = self.env['account.move'].create(move_vals)

                AccountMoveLine.with_context(check_move_validity=False).create(
                    {
                        'journal_id': def_check_journal.id,
                        # 'date': date,
                        'name': name_ref,
                        'account_id': rej_check_account.id,
                        'debit': check.amount,
                        'move_id': move_id.id,
                    }
                )

                AccountMoveLine.with_context(check_move_validity=False).create(
                    {
                        'journal_id': def_check_journal.id,
                        # 'date': date,
                        'name': name_ref,
                        'account_id': check_account.id,
                        'credit': check.amount,
                        'move_id': move_id.id,
                    }
                )
                move_id._post()
                if self.env.context.get('is_expired', False):
                    check.write(
                        {
                            'expired_date': fields.Date.today(),
                            'expired_move_id': move_id.id,
                        }
                    )
                else:
                    check.write(
                        {
                            'cancel_date': fields.Date.today(),
                            'cancel_move_id': move_id.id,
                        }
                    )
            third_party_checks.write({'third_party_check_state': 'cancelled'})
        if issued_checks:
            for check in issued_checks:
                if check.type == 'deferred' and check.accredited:
                    raise ValidationError(
                        _(
                            'Check number %s is postdated and has already been '
                            'accredited!\nPlease break the conciliation of that '
                            'check first.'
                        )
                        % check.number
                    )
            issued_checks.write({'issued_check_state': 'cancelled'})
        if not self.env.context.get('is_expired', False):
            for check in issued_checks + third_party_checks:
                check.message_post(
                    body=_(
                        "Check Cancelled. Reason: %(reason)s. ",
                        reason=reason,
                    )
                )

    def expired_check(self, reason):
        if self.internal_type == 'issued':
            AccountCheckConfig = self.env['account.check.config']
            AccountMoveLine = self.env['account.move.line']
            rej_check_account = AccountCheckConfig.search(
                [('company_id', '=', self.env.company.id)]
            ).expired_issued_checks_account_id
            if not rej_check_account:
                raise UserError(
                    _(
                        "Error! There is no Account configured for rejected issued checks."
                    )
                )
            check_account = AccountCheckConfig.search(
                [('company_id', '=', self.env.company.id)]
            ).deferred_account_id
            if not check_account:
                raise UserError(
                    _(
                        "Error! There is no Account configured for issued checks."
                    )
                )
            def_check_journal = AccountCheckConfig.search(
                [('company_id', '=', self.env.company.id)]
            ).rejected_issued_checks_journal_id
            if not def_check_journal:
                raise UserError(
                    _(
                        "Error! There is no Journal configured for deferred checks."
                    )
                )
            name_ref = 'Cancel Check ' + self.number
            move_vals = {
                'ref': name_ref,
                'journal_id': def_check_journal.id,
                # 'date': date,
            }
            move_id = self.env['account.move'].create(move_vals)

            AccountMoveLine.with_context(check_move_validity=False).create(
                {
                    'journal_id': def_check_journal.id,
                    # 'date': date,
                    'name': name_ref,
                    'account_id': check_account.id,
                    'debit': self.amount,
                    'move_id': move_id.id,
                }
            )

            AccountMoveLine.with_context(check_move_validity=False).create(
                {
                    'journal_id': def_check_journal.id,
                    # 'date': date,
                    'name': name_ref,
                    'account_id': rej_check_account.id,
                    'credit': self.amount,
                    'move_id': move_id.id,
                }
            )
            move_id._post()
            self.write(
                {
                    'expired_date': fields.Date.today(),
                    'expired_move_id': move_id.id,
                    'issued_check_state': 'expired',
                }
            )
        else:
            self.with_context(is_expired=True).cancel_check(reason)
            self.write({'third_party_check_state': 'expired'})

        self.message_post(
            body=_(
                "Check Expired. Reason: %(reason)s. ",
                reason=reason,
            )
        )

    # ISSUED CHECK FIELDS AND METHODS
    issued_check_state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('waiting_debit', 'Waiting debit'),
            ('debited', 'Debited'),
            ('cancelled', 'Cancelled'),
            ('returned', 'Returned'),
            ('rejected', 'Rejected'),
            ('expired', 'Expired'),
        ],
        default='draft',
        string='Issued Check State',
        tracking=True,
    )
    checkbook_id = fields.Many2one(
        comodel_name='account.payment.method.line',
        string='Checkbook ID',
        ondelete='restrict',
        domain=[('payment_method_id.code', '=', 'checks')],
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
        string='Debited', compute='_compute_debit_state'
    )

    @api.depends('clearance_move_id')
    def _compute_debit_state(self):
        for check in self:
            check.accredited = False
            if check.internal_type == 'issued':
                if check.clearance_move_id:
                    check.accredited = True
                else:
                    check.accredited = False

    def debit_checks(self, date):
        """Method for issued checks debitation."""
        AccountCheckConfig = self.env['account.check.config']
        AccountMoveLine = self.env['account.move.line']

        if 'third_party' in self.mapped('internal_type'):
            raise UserError(_("You can't debit a Thirt Party Check"))

        for check in self:
            if check.issued_check_state != "waiting_debit":
                raise ValidationError(
                    _("Check %s can't be debited!") % check.number
                )

        for check in self:
            def_check_account = AccountCheckConfig.search(
                [('company_id', '=', self.env.company.id)]
            ).deferred_account_id
            def_check_journal = AccountCheckConfig.search(
                [('company_id', '=', self.env.company.id)]
            ).deferred_journal_id
            if not def_check_journal:
                raise UserError(
                    _(
                        "Error! There is no Journal configured for deferred checks."
                    )
                )

            name_ref = 'Clearance Check ' + check.number
            move_vals = {
                'ref': name_ref,
                'journal_id': def_check_journal.id,
                'date': date,
            }
            move_id = self.env['account.move'].create(move_vals)

            check.write({'clearance_move_id': move_id.id})

            # Creamos la línea contable que iguala el pago del cheque
            check_move_line_vals = {
                'journal_id': def_check_journal.id,
                'date': date,
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
                    'date': date,
                    'name': name_ref,
                    'account_id': check.checkbook_id.bank_account_id.account_id.id,
                    'credit': check.amount,
                    'move_id': move_id.id,
                }

                AccountMoveLine.with_context(check_move_validity=False).create(
                    bank_move_line_vals
                )
                move_id._post()
                # move_lines_to_reconcile = []
                # payment_move_line = move_line_obj.search([
                #     ('issued_check_id', '=', check.id)])
                # move_lines_to_reconcile.append(payment_move_line.id)
                # move_lines_to_reconcile.append(clearance_move_line.id)
                # reconcile_recordset = move_line_obj.browse(move_lines_to_reconcile)
                # reconcile_recordset.reconcile()

            check.write(
                {
                    'issued_check_state': 'debited',
                    'deposit_date': date,
                    'deposit_bank_id': check.checkbook_id.bank_account_id.id,
                }
            )

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
            check.write({'issued_check_state': 'waiting_debit'})

    @api.model
    def issued_create_voucher_move_line(self):
        voucher = self.payment_order_id

        # Buscamos la cuenta contable para el asiento del cheque
        # Esta cuenta se corresponde con la cuenta de banco de donde
        # pertenece el cheque
        if self.type in ['common', 'deferred']:
            # Buscamos la configuracion de cheques
            config = self.env['account.check.config'].search(
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

        debit = credit = 0.0
        if voucher.type in ('purchase', 'payment'):
            credit = self.amount
        elif voucher.type in ('sale', 'receipt'):
            debit = self.amount
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
            'currency_id': voucher.currency_id.id,
            'amount_currency': sign * self.amount_currency,
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
            ('accredited', 'Accredited'),
            ('delivered', 'Delivered'),
            ('cancelled', 'Cancelled'),
            ('rejected', 'Rejected'),
            ('expired', 'Expired'),
        ],
        default='draft',
        string='Third Party Check State',
        tracking=True,
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
    accredit_move_id = fields.Many2one(
        comodel_name='account.move', string='Accredit Move', readonly=True
    )
    accredit_date = fields.Date(string='Accredit Date', readonly=True)
    debit_note_id = fields.Many2one('account.move', ondelete='set null')

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
        # Se llama desde el botón de la vista de cheque
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
        # Se llama desde la cancelación de la Orden de Pago. Todos los cheques tienen que estar en 'Entregado'
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

    def return_to_draft(self):
        # Se llama desde la cancelación de un Recibo. Todos los cheques tienen que estar en 'En cartera'
        # Es la reversión al método to_wallet
        for check in self.filtered(
            lambda rec: rec.internal_type == 'third_party'
        ):
            if check.third_party_check_state != 'in_wallet':
                raise UserError(
                    _(
                        "Third Check Error! You cannot return to "
                        "draft a check if it is not in In Wallet state"
                    )
                )
        self.write(
            {
                'third_party_check_state': 'draft',
                'source_partner_id': False,
                'origin': False,
                'payment_date': False,
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
        # Buscamos la configuracion de cheques
        config = self.env['account.check.config'].search(
            [('company_id', '=', voucher.company_id.id)]
        )
        if not len(config):
            raise UserError(
                _('ERROR! There is no check configuration for this Company!')
            )

        # TODO: Chequear que funcione bien en
        # multicurrency estas dos lineas de abajo
        # voucher.company_id.currency_id.id
        # self.currency_id.id

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
            'currency_id': voucher.currency_id.id,
            'amount_currency': sign * self.amount_currency,
            'date': voucher.date,
            'date_maturity': self.payment_date or self.issue_date,
        }

        return move_line

    def _get_voucher_type(self, denomination):
        return self.env['res.voucher.type'].search(
            [
                ('denomination', '=', denomination),
                ('doc_type', '=', 'dn'),
                ('afip_code', '<', 200),
            ],
            limit=1,
        )

    def create_debit_note_from_rejected_check(self):
        AccountCheckConfig = self.env['account.check.config']

        for check in self:
            name_ref = 'Debit note for Third Party Check ' + check.number
            check_config = AccountCheckConfig.search(
                [('company_id', '=', check.company_id.id)]
            )
            journals = self.env.user.get_journals_by_fiscal_position(
                check.source_partner_id.property_account_position_id
            )

            if not journals:
                raise ValidationError(
                    _("Partner don't have a properly journal configured.")
                )
            if not check_config.rejected_check_product_id:
                raise ValidationError(
                    _(
                        "You need to configure a product for rejected check first."
                    )
                )

            denomination = journals[0].denomination

            move_vals = {
                'ref': name_ref,
                'partner_id': check.source_partner_id.id,
                'journal_id': journals[0].id,
                'move_type': 'out_invoice',
                'is_debit_note': True,
                'denomination': denomination,
                'created_from_rej_check': True,
                'fiscal_position_id': check.source_partner_id.property_account_position_id.id,
                'invoice_line_ids': [
                    (
                        0,
                        0,
                        {
                            "product_id": check_config.rejected_check_product_id.id,
                            "quantity": 1.0,
                            "name": name_ref,
                            "price_unit": check.amount,
                        },
                    ),
                ],
            }
            # 'voucher_type_id': check._get_voucher_type(denomination),
            move = self.env['account.move'].create(move_vals)
            check.debit_note_id = move.id

            return {
                'name': _('Debit Note'),
                'type': 'ir.actions.act_window',
                'res_model': 'account.move',
                'view_mode': 'form',
                'res_id': move.id,
                'target': 'current',
            }

    def get_formview_id(self, access_uid=None):
        res = super().get_formview_id(access_uid=access_uid)
        if (
            self._context.get('internal_type', '') == 'third_party'
            or self.internal_type == 'third_party'
        ):
            res = self.env.ref(
                'l10n_ar_eynes.account_third_party_check_view_form'
            ).id
        else:
            res = self.env.ref(
                'l10n_ar_eynes.account_issued_check_view_form'
            ).id
        return res

    _sql_constraints = [
        (
            "unique_record",
            "unique(number, checkbook_id, journal_id, checkbook_format)",
            _("This record already exists"),
        ),
    ]
