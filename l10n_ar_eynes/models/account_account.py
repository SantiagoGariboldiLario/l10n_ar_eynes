##############################################################################
#   Copyright (c) 2018 Eynes/E-MIPS (www.eynes.com.ar)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
##############################################################################

import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class AccountAccount(models.Model):
    _name = 'account.account'
    _inherit = 'account.account'

    perception_concept_ids = fields.Many2many(
        comodel_name='perception.concept',
        relation='account_perception_concept_rel',
        column1='account_id',
        column2='concept_id',
        string='Concepts',
    )
    recpam_type = fields.Selection(
        [('reexpressed', 'Reexpressed'), ('no_reexpressed', 'No Reexpressed')],
        'RECPAM',
    )
    retention_concept_ids = fields.Many2many(
        comodel_name='retention.concept',
        relation='account_retention_concept_rel',
        column1='account_id',
        column2='concept_id',
        string='Concepts',
    )

    def get_perceptions_applications(self, fiscal_position):
        self.ensure_one()
        return (
            self.env['perception.tax.application']
            .search([('concept_id', 'in', self.perception_concept_ids.ids)])
            .filtered(
                lambda application: application.perception_tax_id
                in fiscal_position.perception_ids
            )
        )
