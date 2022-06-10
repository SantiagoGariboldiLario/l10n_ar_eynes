from odoo import fields, models


class IIBBSituation(models.Model):
    _name = 'iibb.situation'
    _description = 'IIBB Situation'

    name = fields.Char(string='Name', required=True)
