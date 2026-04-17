import logging

from odoo import api, fields, models
from odoo.fields import Domain

_logger = logging.getLogger(__name__)


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    pos_config_id = fields.Many2one(
        comodel_name='pos.config',
        string='Pos Config',
    )
    wsfe_pos_config_id = fields.Many2one(
        comodel_name='pos.config',
        string='WSFE Pos Config',
    )

    def get_pretty_denomination(self):
        denom_attrs = self._fields['denomination'].get_description(self.env)
        denomination = list(
            filter(
                lambda x: x[0] == self.denomination,
                denom_attrs['selection'],
            )
        )
        return denomination[0][1] if denomination else False

    @api.model
    def name_search(self, name='', domain=None, operator='ilike', limit=100):
        """Filter out POS journals when context flag is set (v19 signature)."""
        if self.env.context.get('no_journal_in_pos'):
            domain = Domain.AND(
                [
                    domain or [],
                    [
                        ('pos_config_id', '=', False),
                        ('wsfe_pos_config_id', '=', False),
                    ],
                ]
            )
        # Call super with positional args only to avoid unexpected kw errors.
        return super().name_search(name or '', domain or [], operator, limit)
