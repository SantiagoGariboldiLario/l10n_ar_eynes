import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = 'res.company'

    fcons_max_amount = fields.Float(
        string='Monto Máximo Consumidor Final',
        default=417288,
        help="Maximun amount that invoice can be emitted to Final Consumer without identification. When you "
        "are making an invoice on PdV and it exceeds this amount, you will receive and alert before send it to ARCA.",
    )

    def get_fc_max_amount(self):
        return self.fcons_max_amount
