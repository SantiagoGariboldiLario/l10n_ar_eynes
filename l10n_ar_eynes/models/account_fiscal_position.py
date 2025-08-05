from odoo import fields, models


class AccountFiscalPosition(models.Model):
    _name = 'account.fiscal.position'
    _inherit = 'account.fiscal.position'

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
    internal_taxes_ids = fields.Many2many(
        comodel_name='account.tax',
        relation='fiscal_position_internal_rel',
        column1='position_id',
        column2='internal_tax_id',
        string='Internal Taxes',
        domain=lambda self: [
            ('tax_group_id.group_type', '=', 'internals'),
            ('company_id', '=', self.env.company.id),
            ('type_tax_use', '=', 'sale'),
        ],
        help="These are the internal taxes that will be applied to Customers "
        + "belonging to this Fiscal Position.",
    )
    retention_ids = fields.Many2many(
        comodel_name='account.tax',
        relation='fiscal_position_retention_rel',
        column1='position_id',
        column2='retention_id',
        string='Retentions',
        domain=lambda self: [
            ('tax_group_id.group_type', '=', 'retention'),
            ('company_id', '=', self.env.company.id),
            ('type_tax_use', '=', 'purchase'),
        ],
        help="These are the retentions that will be applied to Suppliers "
        + "belonging to this Fiscal Position. Exceptions to this have to be "
        + "loaded at partner form.",
    )
    perception_ids = fields.Many2many(
        comodel_name='account.tax',
        relation='fiscal_position_perception_rel',
        column1='position_id',
        column2='perception_id',
        string='Perceptions',
        domain=lambda self: [
            ('tax_group_id.group_type', '=', 'perception'),
            ('company_id', '=', self.env.company.id),
            ('type_tax_use', '=', 'sale'),
        ],
        help="These are the perceptions that will be applied to Customers "
        "belonging to this Fiscal Position. Exceptions to this have to be "
        "loaded at partner form.",
    )
    local = fields.Boolean(
        string='Local Fiscal Rules',
        default=True,
        help='Check this if it corresponds to apply local fiscal rules, '
        'like invoice number validation, etc.',
    )
    is_final_consumer = fields.Boolean("Is Final Consumer")

    def unlink(self):
        """ Override unlink to prevent remove fiscal positions """
        for fiscal_position in self:
            # This prevents the deletion of fiscal positions with IDs 1 to 20,
            # which are typically reserved for system use or default fiscal positions.
            if fiscal_position.id in range(1, 21):
                return
        return super().unlink()
