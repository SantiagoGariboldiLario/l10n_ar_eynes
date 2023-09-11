##############################################################################
#
#   Copyright (c) 2022-2023 Eynes SRL  (Eynes - Ingenieria del software)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
#
##############################################################################

import logging

from odoo import models

_logger = logging.getLogger(__name__)


class StockMove(models.Model):
    _inherit = "stock.move"

    def _action_confirm(self, merge=True, merge_into=False):
        res = super(StockMove, self)._action_confirm(
            merge=merge, merge_into=merge_into
        )

        picking = self.picking_id
        if picking.carrier_id:
            picking.write({"dom_partner_id": picking.carrier_id.id})
        return res
