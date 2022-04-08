from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    customer = fields.Boolean(string='Is Customer')
