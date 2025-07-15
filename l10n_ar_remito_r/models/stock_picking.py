from odoo import fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    bulk = fields.Integer(string="Bultos")
