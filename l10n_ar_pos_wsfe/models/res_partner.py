import logging

from odoo import models

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def check_final_consumer_without_vat(self):
        return self.property_account_position_id == self.env.ref(
            'l10n_ar_eynes.fiscal_position_cf'
        ) and self.document_type_id == self.env.ref(
            'l10n_ar_eynes.document_doc_otro'
        )
