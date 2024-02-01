# -- coding: utf-8 --
##############################################################################
#
#   Copyright (c) 2022-2023 Eynes SRL (Eynes - Ingenieria del software)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
#
##############################################################################

import logging
from odoo import fields, models

_logger = logging.getLogger(__name__)


class AccountAccount(models.Model):
    _inherit = 'account.account'

    recpam_type = fields.Selection(
        [('reexpressed', 'Reexpressed'), ('no_reexpressed', 'No Reexpressed')], 'RECPAM'
    )
