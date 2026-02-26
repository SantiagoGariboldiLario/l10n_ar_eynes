from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    use_special_padron = fields.Boolean()
