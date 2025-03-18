##############################################################################
#
#   Copyright (c) 2025 Eynes SRL  (Eynes - Ingenieria del software)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
#
##############################################################################

from odoo import _, fields, models


class ProductArea(models.Model):
    _name = "product.area"

    active = fields.Boolean(default=True)
    code = fields.Integer(required=True)
    name = fields.Char('Description', required=True)

    _sql_constraints = [
        (
            'unique_area_code',
            'unique(code)',
            _('This code is used.'),
        )
    ]
