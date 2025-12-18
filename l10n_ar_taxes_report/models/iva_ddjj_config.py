from odoo import fields, models


class IVADDJJConfig(models.Model):
    _name = "iva.ddjj.config"
    _description = "IVA DDJJ Report Configuration"

    company_id = fields.Many2one('res.company', string="Company")
    free_availability_balance_account_id = fields.Many2one(
        'account.account',
        string="Free Availability Balance Account",
        required=True,
    )
    last_period_balance_account_id = fields.Many2one(
        'account.account',
        string="Last Period Balance Account",
        required=True,
    )
    name = fields.Char(string="Configuration Name", required=True)
