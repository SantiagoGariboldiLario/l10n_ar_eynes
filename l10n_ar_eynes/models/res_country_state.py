##############################################################################
#
#   Copyright (c) 2022-2023 Eynes SRL  (Eynes - Ingenieria del software)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
#
##############################################################################

import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class ResCountryState(models.Model):
    _inherit = "res.country.state"

    cot_code = fields.Char(string="COT Code", size=2)
    cot_valid = fields.Boolean(string="COT Valid")
