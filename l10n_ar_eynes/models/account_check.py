from odoo import fields, models, _, api


class AccountCheck(models.Model):
    _name = 'account.check'
    _description = 'Check'

    name = fields.Char('Check Number', required=True)

    bank_account_id = fields.Many2one(comodel_name='account.journal', string='Bank Account', required=True)
    checkbook_id = fields.Many2one(
        comodel_name='account.payment.method.line',
        string='Checkbook ID',
        ondelete='restrict',
    )
    checkbook_format = fields.Selection(
        selection=[('physical', 'Physical'), ('virtual', 'Virtual'), ('echeq', 'Echeq')],
        string='Format',
        required=True
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('waiting', 'Waiting Accreditation'),
            ('issued', 'Issued'),
            ('cancel', 'Cancelled'),
            ('rejected', 'Rejected')
        ],
        default='draft',
        string='State',
        required=True,
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
        default='issued',
        required=True
    )

    amount = fields.Float(string='Amount')
    receiving_partner_id = fields.Many2one(comodel_name='res.partner', string='Receiving Entity')

    issue_date = fields.Date(string='Issue Date')
    reception_date = fields.Date(string='Reception Date')
    payment_date = fields.Date(string='Payment Date', help="Only if this check is post dated")

    crossed = fields.Boolean(string='Crossed')
    not_order = fields.Boolean(string='Not Order')

    clearing = fields.Selection(
        selection=[
            ('24', '24 hs'),
            ('48', '48 hs'),
            ('72', '72 hs')
        ],
        string='Clearing',
        default='24'
    )
    origin = fields.Char(string='Origin', size=64)
    signatory = fields.Char(string='Signatory', size=64)

    note = fields.Text(string="Note")

    payment_move_id = fields.Many2one(comodel_name='account.move', string='Payment Account Move')
    clearance_move_id = fields.Many2one(comodel_name='account.move', string='Clearance Account Move')

    accredited = fields.Boolean(string='Accredited', compute='_compute_accredit_state')

    @api.depends('clearance_move_id')
    def _compute_accredit_state(self):
        for check in self:
            if check.clearance_move_id:
                check.accredited = True
            else:
                check.accredited = False

    _sql_constraints = [
        ("unique_record", "unique(name, checkbook_id, bank_account_id, checkbook_format)", _("This record already exists")),
    ]
