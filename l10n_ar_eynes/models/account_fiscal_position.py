from odoo import fields, models


class AccountFiscalPosition(models.Model):
    _name = 'account.fiscal.position'
    _inherit = 'account.fiscal.position'

    supplier_denomination = fields.Selection(
        selection=[
            ("a", "A"), ("b", "B"),
            ("c", "C"), ("e", "E"),
            ("not_defined", "Not Defined")
        ],
        string='Supplier Denomination',
        required=True,
        default='not_defined'
    )

    afip_code = fields.Integer(string="AFIP Code")
