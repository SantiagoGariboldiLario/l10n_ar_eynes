import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def _fix_aduana_fiscal_position(cr):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env.ref('l10n_ar_eynes.fiscal_position_a').write(
        {
            'local': False,
            'supplier_denomination': 'ana',
        }
    )


def migrate(cr, version):
    _logger.info(
        "Change Aduana fiscal position to not local and denomination ANA..."
    )
    _fix_aduana_fiscal_position(cr)
