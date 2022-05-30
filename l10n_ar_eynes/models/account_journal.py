from odoo import fields, models


class AccountJournal(models.Model):
    _name = "account.journal"
    _description = "Journal"
    _inherit = "account.journal"

    def get_default_warehouse(self):
        return self.env['stock.warehouse'].browse(1).id

    code = fields.Char(
        string='POS code',
        size=5,
        required=True,
        help="Point of sale reference code",
        default='')

    denomination = fields.Selection(
        [("a", "A"), ("b", "B"), ("c", "C"), ("e", "E"), ("not_defined", "Not Defined")],
        string='Denomination',
        default='not_defined')

    fiscal_position_id = fields.Many2one(
        comodel_name='account.fiscal.position',
        string='Fiscal Position')

    activity_start_date = fields.Date(
        string="Activity Start Date",
        default=fields.date.today())

    warehouse_id = fields.Many2one(
        comodel_name='stock.warehouse',
        string='Warehouse',
        default=get_default_warehouse)

    due_date = fields.Date(
        string='Due Date',
        help='after this expiration date, account moves are not allowed to use this journal till its extended')

    type = fields.Selection(
        selection_add=[
            ('receipt', 'Receipt'),
            ('payment', 'Payment'),
            ('third_party_checks', 'Third party checks'),
            ('retentions', 'Retentions'),
            ('perceptions', 'Perceptions')
        ],
        ondelete={
            'receipt': lambda recs: recs.write({'type': 'general'}),
            'payment': lambda recs: recs.write({'type': 'general'}),
            'third_party_checks': lambda recs: recs.write({'type': 'general'}),
            'retentions': lambda recs: recs.write({'type': 'general'}),
            'perceptions': lambda recs: recs.write({'type': 'general'}),
        }
    )

    # RETENTIONS FIELDS
    general_resolution = fields.Char('GR Number', required=False, size=64)
    notes = fields.Text('Notes')
    tax_id = fields.Many2one(
        comodel_name='account.tax',
        string='Tax'
    )
    type_tax_use = fields.Selection(
        string='Tax Application',
        related='tax_id.type_tax_use',
        readonly=True,
    )
    check_sit_iibb = fields.Boolean(
        string='Check IIBB Situation',
        default=False,
        help="If checked, when IIBB situation is Multilateral, "
        + "this perception is always applicable"
    )
    always_apply_padron = fields.Boolean(
        'Always Apply from Padron',
        default=False,
        help="If checked, when the partner has a perception exception "
        + "and it was generated from a padron, this perception will be applied"
    )
    jurisdiccion = fields.Selection(
        selection=[
            ('nacional', 'Nacional'),
            ('provincial', 'Provincial'),
            ('municipal', 'Municipal'),
        ],
        default='nacional',
    )
    state_id = fields.Many2one(
        comodel_name='res.country.state',
        string='State/Province',
        domain="[('country_id','=','Argentina')]",
    )
    applicable_state = fields.Selection(
        selection=[
            ('dest', 'Destination'),
            ('source', 'Source'),
            ('always', 'Always')
        ],
        string='Applicable State',
        default='dest',
        help="Indicates if this Perception is applicable when:\n"
        "* State/Province is equals to source address\n"
        "* State/Province is equals to destination address\n"
        "* Always"
    )
    from_register_ARBA = fields.Boolean('From ARBA Register')
    from_register_AGIP = fields.Boolean('From AGIP Register')
    retention_type = fields.Selection(
        selection=[
            ('vat', 'VAT'),
            ('gross_income', 'Gross Income'),
            ('profit', 'Profit'),
            ('other', 'Other'),
        ],
        string='Type',
        required=True,
    )
    vat_application_ids = fields.One2many(
        comodel_name='retention.tax.application',
        inverse_name='retention_id',
        string='VAT Tax Application',
        domain=[('type', '=', 'vat')]
    )
    profit_application_ids = fields.One2many(
        comodel_name='retention.tax.application',
        inverse_name='retention_id',
        string='Profit Tax Application',
        domain=[('type', '=', 'profit')]
    )
    gi_application_ids = fields.One2many(
        comodel_name='retention.tax.application',
        inverse_name='retention_id',
        string='Gross Income Tax Application',
        domain=[('type', '=', 'gross_income')]
    )

    _sql_constraints = [
        ('code_unique', 'unique(code)', 'code already exists!')
    ]
