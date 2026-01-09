import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class PosConfig(models.Model):
    _inherit = 'pos.config'

    block_invoice_offline = fields.Many2many(
        'account.fiscal.position',
        'pos_config_fiscal_position_rel',
        'pos_config_id',
        'fiscal_position_id',
        string='Block RI Invoices Offline',
        default=True,
        help="The POS will block the validation of invoices for "
        "customers classified with this Fiscal Positions when the system "
        "is offline, to avoid issues with perception calculations.",
    )
    default_invoice_mode = fields.Selection(
        [('manual', 'Manual'), ('electronic', 'Electronic')],
        default='electronic',
    )
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
    fcons_max_amount = fields.Float(
        string='Monto Máximo Consumidor Final',
        default=417288,
        help="Maximun amount that voucher can be emitted to Final Consumer without identification.",
    )
