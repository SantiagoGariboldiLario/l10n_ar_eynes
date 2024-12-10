import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class PosConfig(models.Model):
    _inherit = 'pos.config'

    invoice_journal_ids = fields.One2many(
        comodel_name='account.journal',
        inverse_name='wsfe_pos_config_id',
        string='Invoice Journals',
        domain="[('type', '=', 'sale'), ('fiscal_type', '=', 'electronic')]",
        help="Accounting journals used to create electronic invoices.",
    )
    invoice_manual_journal_ids = fields.One2many(
        comodel_name='account.journal',
        inverse_name='pos_config_id',
        string='WSFE Invoice Journals',
        domain="[('type', '=', 'sale'), ('fiscal_type', '=', 'internal')]",
        help="Accounting journals used to create invoices.",
    )
