import logging

import psycopg2

_logger = logging.getLogger(__name__)


def update_move_internal_number(cr):
    try:
        cr.execute(
            """
            UPDATE account_move
            SET internal_number = name
            WHERE move_type ilike 'out_%' AND state = 'posted'
        """
        )
    except psycopg2.ProgrammingError:
        cr.rollback()
    return True


def migrate(cr, version):
    _logger.info("""Updating m2m""")
    return update_move_internal_number(cr)
