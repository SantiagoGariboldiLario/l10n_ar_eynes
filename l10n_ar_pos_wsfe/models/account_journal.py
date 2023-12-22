import logging

from odoo import api, fields, models
from odoo.osv import expression

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

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        if self.env.context.get('no_journal_in_pos'):
            args = expression.AND(
                [
                    args or [],
                    [
                        ('pos_config_id', '=', False),
                        ('wsfe_pos_config_id', '=', False),
                    ],
                ]
            )
        return super(AccountJournal, self).name_search(
            name=name,
            args=args,
            operator=operator,
            limit=limit,
        )
