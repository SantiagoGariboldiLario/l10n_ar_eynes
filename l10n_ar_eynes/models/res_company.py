##############################################################################
#
#   Copyright (c) 2022-2023 Eynes SRL  (Eynes - Ingenieria del software)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
#
##############################################################################

import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = "res.company"

    door = fields.Char(
        string="Door",
        related="partner_id.door",
        size=3,
        store=True,
    )
    floor = fields.Char(
        string="Floor",
        related="partner_id.floor",
        size=3,
        store=True,
    )
    num = fields.Char(
        string="Number",
        related="partner_id.floor",
        size=5,
        store=True,
    )
    apartment = fields.Char(
        string="Apartment",
        related="partner_id.apartment",
        store=True,
    )
