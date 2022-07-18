from odoo import fields, models


class AccountTax(models.Model):
    _inherit = 'account.tax'

    afip_code = fields.Char(string="AFIP Code", size=4)
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
        help='Retention type'
    )
    vat_application_ids = fields.One2many(
        comodel_name='retention.tax.application',
        inverse_name='retention_tax_id',
        string='VAT Tax Application',
        domain=[('type', '=', 'vat')]
    )
    profit_application_ids = fields.One2many(
        comodel_name='retention.tax.application',
        inverse_name='retention_tax_id',
        string='Profit Tax Application',
        domain=[('type', '=', 'profit')]
    )
    gi_application_ids = fields.One2many(
        comodel_name='retention.tax.application',
        inverse_name='retention_tax_id',
        string='Gross Income Tax Application',
        domain=[('type', '=', 'gross_income')]
    )
    sequence_to_use = fields.Many2one(
        comodel_name='ir.sequence',
        string='Sequence to use'
    )
    general_resolution = fields.Char('GR Number', required=False, size=64)
    notes = fields.Text('Notes')

    tax_group_name = fields.Char(
        string='Tax group name',
        related='tax_group_id.name'
    )
