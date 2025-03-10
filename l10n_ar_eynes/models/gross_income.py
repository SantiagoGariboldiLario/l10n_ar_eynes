from odoo import fields, models


class GrossIncome(models.Model):
    _name = "gross.income"

    partner_id = fields.Many2one("res.partner")
    province_id = fields.Many2one(
        "res.country.state",
        string="Provincias",
        domain="[('country_id', '=', 'Argentina')]",
    )
    type_taxpayer = fields.Selection(
        [
            ('local', 'Local'),
            ('CM', 'CM'),
            ('CMsede', 'CM-Sede'),
            ('sin_actividad', 'Sin Actividad'),
        ],
        string="Type of taxpayer",
    )
