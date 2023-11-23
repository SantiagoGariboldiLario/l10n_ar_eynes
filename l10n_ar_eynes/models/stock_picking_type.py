from odoo import fields, models

class PickingType(models.Model):
    _inherit = "stock.picking.type"

    # Secuencia para renumerar el stock.picking luego de una transferencia
    # Es opcional, por lo tanto, puede servirnos para cuando son Delivery Orders
    # y dependen del Warehouse, por lo tanto, podemos tener para varias sucursales
    sequence_transfer_id = fields.Many2one('ir.sequence', string='Sequence After Transfer', required=False)
