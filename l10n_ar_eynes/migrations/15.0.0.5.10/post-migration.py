import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def update_move_name(cr):
    env = api.Environment(cr, SUPERUSER_ID, {})
    invoices = env['account.move'].search(
        [
            ('move_type', 'in', ['in_invoice', 'in_refund']),
            ('state', '=', 'draft'),
        ]
    )
    invoices._compute_name()
    return True


def migrate(cr, version):
    _logger.info("""Updating computed field 'name' for suppliers""")
    return update_move_name(cr)
