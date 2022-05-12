from odoo import fields, models, _, api
from odoo.exceptions import ValidationError, UserError


class AccountCheckConfig(models.Model):
    _name = 'account.check.config'
    _description = 'Check Account Configuration'

    account_id = fields.Many2one(
        comodel_name='account.account',
        string='Main Check Account',
        required=True,
        help="In Argentina, Valores a Depositar is used, for example"
    )
    deferred_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Deferred Check Account',
        required=True
    )
    deferred_journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Deferred Check Journal',
        required=True
    )
    receivable_rejected_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Receivable Rejected Check Account',
        domain=[('internal_type', '=', 'receivable')],
        help=_("Partner's account in debit note generation."),
        required=True
    )
    rejected_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Rejected Check Account',
        domain=[('internal_type', 'not in', ('receivable', 'payable'))],
        required=True
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.user.company_id.id
    )

    def name_get(self):
        ret = []
        for config in self:
            ret.append((config.id, "%s: %s" % (
                config.company_id.name, config.account_id.name)))
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
        default=_get_default_journal
    )
    bank_id = fields.Many2one(
        comodel_name='res.bank',
        string='Bank'
    )
    checkbook_id = fields.Many2one(
        comodel_name='account.payment.method.line',
        string='Checkbook ID',
        ondelete='restrict',
        domain=[('payment_method_id.code', '=', 'check_printing')]
    )
    checkbook_format = fields.Selection(
        selection=[
            ('physical', 'Physical'),
            ('virtual', 'Virtual'),
            ('echeq', 'Echeq')
        ],
        string='Format',
        required=True
    )
    type = fields.Selection(
        selection=[('common', 'Common'), ('deferred', 'Deferred')],
        string='Type',
        default='common',
        required=True
    )
    internal_type = fields.Selection(
        selection=[('issued', 'Issued'), ('third_party', 'Third Party')],
        string='Internal Type',
        default='third_party',
        required=True
    )
    amount = fields.Float(string='Amount')
    receiving_partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Receiving Entity'
    )
    issue_date = fields.Date(string='Issue Date')
    reception_date = fields.Date(string='Reception Date')
    reject_date = fields.Date(string='Reject Date')
    payment_date = fields.Date(
        string='Payment Date',
        help="Only if this check is post dated"
    )
    crossed = fields.Boolean(string='Crossed')
    not_order = fields.Boolean(string='Not Order')
    clearing = fields.Selection(
        selection=[('24', '24 hs'), ('48', '48 hs'), ('72', '72 hs')],
        string='Clearing',
        default='24'
    )
    origin = fields.Char(string='Origin', size=64)
    signatory = fields.Char(string='Signatory', size=64)
    note = fields.Text(string="Note")
    payment_move_id = fields.Many2one(
        comodel_name='account.move',
        string='Payment Account Move'
    )
    clearance_move_id = fields.Many2one(
        comodel_name='account.move',
        string='Clearance Account Move'
    )
    accredited = fields.Boolean(
        string='Accredited',
        compute='_compute_accredit_state'
    )

    @api.depends('clearance_move_id')
    def _compute_accredit_state(self):
        for check in self:
            if check.clearance_move_id:
                check.accredited = True
            else:
                check.accredited = False

    def unlink(self):
        """method gets overrided to ensure that check must be in specif state to get deleted"""

        for check in self:
            if check.internal_type == 'third_party':
                if check.third_party_check_state != 'in_wallet':
                    raise UserError(
                        _("Check Error! You cannot delete a third check that is not in Wallet")
                    )
            elif check.internal_type == 'issued':
                if check.issued_check_state != 'draft':
                    raise UserError(
                        _("Check Error! You cannot delete a check that is not in Draft")
                    )
        return super(AccountCheck, self).unlink()

    # ISSUED CHECK FIELDS AND METHODS
    issued_check_state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('waiting_accreditation', 'Waiting accreditation'),
            ('cancelled', 'Cancelled'),
            ('paid', 'Paid'),
            ('expired', 'Expired'),
            ('rejected', 'Rejected'),
            ('waiting_numeration', 'Waiting numeration')
        ],
        default='draft',
        string='State'
    )
    payment_order_id = fields.Many2one(
        comodel_name='account.payment.order',
        string='Payment Order',
        ondelete='cascade'
    )

    # THIRD PARTY CHECK FIELDS AND METHODS
    third_party_check_state = fields.Selection(
        selection=[
            ('in_wallet', 'In wallet'),
            ('deposited', 'Deposited'),
            ('delivered', 'Delivered'),
            ('rejected', 'Rejected'),
            ('returned', 'Returned')
        ],
        default='in_wallet',
        string='State'
    )
    deposit_bank_id = fields.Many2one(
        comodel_name='res.partner.bank',
        string='Deposit Account'
    )
    source_payment_order_id = fields.Many2one(
        comodel_name='account.payment.order',
        string='Source Payment Order',
        ondelete="cascade",
        readonly=True
    )
    debit_note_id = fields.Many2one(
        comodel_name='account.move',
        string='Debit Note',
        readonly=True,
        help="In case of rejection of the third check"
    )
    source_partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Source Partner',
        required=False,
        readonly=True
    )
    destiny_partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Destiny Partner'
    )
    deposit_move_id = fields.Many2one(
        comodel_name='account.move',
        string='Deposit Move',
        readonly=True
    )
    deposit_journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Deposit Journal',
        readonly=True,
        compute='_compute_deposit_journal_id'
    )
    bank_branch = fields.Char(string='Bank Branch', size=64)
    zip = fields.Char(string='Zip Code', size=64)
    endorsement_date = fields.Date(string='Endorsement Date')
    deposit_date = fields.Date(string='Deposit Date', readonly=True)
    signatory_vat = fields.Char(string='Signatory VAT', size=64)
    signatory_account = fields.Char(string='Signatory account', size=64)
    deposit_slip = fields.Char(string='Deposit Slip', size=64)
    dest = fields.Char(string='Destiny', size=64)

    @api.depends('deposit_move_id')
    def _compute_deposit_journal_id(self):
        for check in self.filtered(lambda rec: rec.internal_type == 'third_party'):
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

    _sql_constraints = [
        ("unique_record", "unique(number, checkbook_id, journal_id, checkbook_format)", _("This record already exists")),
    ]
