from odoo import fields, models, _, api
from odoo.exceptions import ValidationError


class AccountCheck(models.Model):
    _name = 'account.check'
    _description = 'Check'
    _rec_name = 'number'

    number = fields.Char('Check Number', required=True, size=8)

    bank_account_id = fields.Many2one(
        comodel_name='account.journal',
        string='Journal',
        required=True,
        domain=[('type', '=', 'bank')])

    bank_id = fields.Many2one(
        comodel_name='res.bank',
        related='bank_account_id.bank_id',
        string='Bank')

    checkbook_id = fields.Many2one(
        comodel_name='account.payment.method.line',
        string='Checkbook ID',
        ondelete='restrict',
        domain=[('payment_method_id.code', '=', 'check_printing')])

    checkbook_format = fields.Selection(
        selection=[
            ('physical', 'Physical'),
            ('virtual', 'Virtual'),
            ('echeq', 'Echeq')
        ],
        string='Format',
        required=True)

    type = fields.Selection(
        selection=[('common', 'Common'), ('deferred', 'Deferred')],
        string='Type',
        default='common',
        required=True)

    internal_type = fields.Selection(
        selection=[('issued', 'Issued'), ('third_party', 'Third Party')],
        string='Internal Type',
        default='third_party',
        required=True)

    amount = fields.Float(string='Amount')

    receiving_partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Receiving Entity')

    issue_date = fields.Date(string='Issue Date')
    reception_date = fields.Date(string='Reception Date')

    payment_date = fields.Date(
        string='Payment Date',
        help="Only if this check is post dated")

    crossed = fields.Boolean(string='Crossed')
    not_order = fields.Boolean(string='Not Order')

    clearing = fields.Selection(
        selection=[
            ('24', '24 hs'),
            ('48', '48 hs'),
            ('72', '72 hs')
        ],
        string='Clearing',
        default='24')

    origin = fields.Char(string='Origin', size=64)
    signatory = fields.Char(string='Signatory', size=64)

    note = fields.Text(string="Note")

    account_payment_order_id = fields.Many2one(
        comodel_name='account.payment.order',
        string='Account payment order',
        ondelete='cascade')

    payment_move_id = fields.Many2one(
        comodel_name='account.move',
        string='Payment Account Move')

    clearance_move_id = fields.Many2one(
        comodel_name='account.move',
        string='Clearance Account Move')

    accredited = fields.Boolean(
        string='Accredited',
        compute='_compute_accredit_state')

    @api.depends('clearance_move_id')
    def _compute_accredit_state(self):
        for check in self:
            if check.clearance_move_id:
                check.accredited = True
            else:
                check.accredited = False

    def reject_check(self, state):
        """
            This function is called by the any of the reject wizard actions (issued or 3rd party).
            It updates de state of the rejected check. Since both type of check are combined in a single class,
            the function takes a 2nd argument to choose which one of the state needs to be updated.

        Args:
            state (selection): this argument can take 2 values:
                issued_check_state or third_party_check_state.
        """
        self.write({
            state : 'rejected',
        })

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
        string='State')

    # THIRD PARTY CHECK FIELDS AND METHODS
    third_party_check_state = fields.Selection(
        selection=[
            ('in_wallet', 'In wallet'),
            ('deposited', 'Deposited'),
            ('delivered', 'Delivered'),
            ('rejected', 'Rejected')
        ],
        default='in_wallet',
        string='State')

    deposit_move_id = fields.Many2one(
        comodel_name='account.move',
        string='Deposit Move',
        readonly=True)

    deposit_journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Deposit Journal',
        readonly=True,
        compute='_compute_deposit_journal_id')

    signatory_vat = fields.Char(string='Signatory VAT', size=64)
    signatory_account = fields.Char(string='Signatory account', size=64)
    deposit_slip = fields.Char(string='Deposit Slip', size=64)

    @api.depends('deposit_move_id')
    def _compute_deposit_journal_id(self):
        for check in self.filtered(lambda rec: rec.interal_type == 'third_party'):
            if check.deposit_move_id:
                check.deposit_journal_id = check.deposit_move_id.journal_id
            else:
                check.deposit_journal_id = False

    @api.onchange('number')
    def _onchange_number(self):
        if not self.number:
            return
        if not self.number.isnumeric():
            raise ValidationError(_('Check Number must not have non numerical characters'))
        self.number = self.number.zfill(8)

    def deposit_check(self):
        """
            This function is called after the deposit_check action is executed.
            It updates the state of the check to 'deposited'.
            Since the button is only on 3rd party checks, it doesn't need another argument.
        """
        self.write({
            'third_party_check_state' : 'deposited'
        })

    _sql_constraints = [
        ("unique_record", "unique(name, checkbook_id, bank_account_id, checkbook_format)", _("This record already exists")),
    ]
