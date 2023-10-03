import logging

import psycopg2

_logger = logging.getLogger(__name__)


def fix_wsfe_view(cr):
    try:
        cr.execute(
            """
            DELETE FROM ir_ui_view
            WHERE arch_db ilike '%homologation%'
                and model = 'wsfe.config'
            """
        )
    except psycopg2.ProgrammingError:
        cr.rollback()
    return True


def migrate(cr, version):
    _logger.info("""Fixing WSFE view...""")
    return fix_wsfe_view(cr)
