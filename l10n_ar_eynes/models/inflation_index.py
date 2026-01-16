##############################################################################
#
#   Copyright (c) 2022-2023 Eynes SRL (Eynes - Ingenieria del software)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
#
##############################################################################

import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class InflationIndex(models.Model):
    _name = 'inflation.index'
    _description = 'Inflation Index'
    _rec_name = 'date'

    coefficient = fields.Float('Coefficient')
    date = fields.Date('Date')
