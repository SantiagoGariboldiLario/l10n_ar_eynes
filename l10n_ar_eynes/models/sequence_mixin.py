##############################################################################
#
#   Copyright (c) 2022-2023 Eynes SRL  (Eynes - Ingenieria del software)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
#
##############################################################################

import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class SequenceMixin(models.AbstractModel):
    _inherit = 'sequence.mixin'

    @api.model
    def _deduce_sequence_number_reset(self, name):
        """
        We have modified the structure of base field 'name' of account.move for invoices.
            base: INV/AAAA/XXXXX (prefix-year-sequence)
            l10n_ar_eynes: XXXXX-XXXXXXXX (POS-sequence)
        'name' is setted from base account module as a sequence field, that needs to be checked.
        (We can check it in _compute_name() -> move._constrains_date_sequence())


        This function deduce the structure of that field based in the original method,
        using a regular expression to compare it.
        But, when we use some POS like '2149' it seems to be a year and its treated like that,
        so this function returns 'year'
        an then the sequence field is compared with the actual date and produces an error.
        We need to force to return 'never'. By this way, the POS number becomes
        a prefix and only the sequence is compared.
        """
        if self._name == 'account.move' and (
            self.is_sale_document(include_receipts=True)
            or self.is_purchase_document(include_receipts=True)
        ):
            return 'never'
        return super()._deduce_sequence_number_reset(name)
