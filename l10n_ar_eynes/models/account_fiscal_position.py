from odoo import api, fields, models


class AccountFiscalPosition(models.Model):
    _name = 'account.fiscal.position'
    _inherit = 'account.fiscal.position'

    @api.model
    def _get_perceptions_domain(self):
        company = self.env.user.company_id
        return [
            '|',
            ('company_id', '=', False),
            ('company_id', '=', company.id),
        ]

    supplier_denomination = fields.Selection(
        selection=[
            ("a", "A"),
            ("b", "B"),
            ("c", "C"),
            ("e", "E"),
            ('m', 'M'),
            ('oc', 'OC'),
            ("not_defined", "Not Defined"),
        ],
        string='Supplier Denomination',
        required=True,
        default='not_defined',
    )
    afip_code = fields.Integer(string="AFIP Code")
    retention_ids = fields.Many2many(
        comodel_name='account.journal',
        relation='fiscal_position_retention_rel',
        column1='position_id',
        column2='retention_id',
        string='Retentions',
        domain=lambda self: [
            ('type', '=', 'retentions'),
            ('company_id', '=', self.env.user.company_id.id),
        ],
        help="These are the retentions that will be applied to Suppliers "
        + "belonging to this Fiscal Position. Exceptions to this have to be "
        + "loaded at partner form.",
    )
    perception_ids = fields.Many2many(
        'perception.perception',
        'fiscal_position_perception_rel',
        'position_id',
        'perception_id',
        'Perceptions',
        domain=lambda self: self._get_perceptions_domain(),
        help="These are the perceptions that will be applied to Suppliers "
        "belonging to this Fiscal Position. Exceptions to this have to be "
        "loaded at partner form.",
    )
    local = fields.Boolean(
        string='Local Fiscal Rules',
        default=True,
        help='Check this if it corresponds to apply local fiscal rules, '
        'like invoice number validation, etc.',
    )
