from odoo import fields, models


class AccountTax(models.Model):
    _inherit = 'account.tax'

    afip_code = fields.Char(string="AFIP Code", size=4)
