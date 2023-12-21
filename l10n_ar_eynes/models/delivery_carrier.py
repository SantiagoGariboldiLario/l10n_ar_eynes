###############################################################################
#   Copyright (c) 2022-2023 Eynes SRL  (Eynes - Ingenieria del software)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
###############################################################################

import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class DeliveryCarrier(models.Model):
    _inherit = 'delivery.carrier'

    vat = fields.Char(
        string='VAT',
    )
    document_type_id = fields.Many2one(
        comodel_name='res.document.type', string='Document type'
    )
