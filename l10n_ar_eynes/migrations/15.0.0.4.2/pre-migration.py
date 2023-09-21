import logging

import psycopg2

_logger = logging.getLogger(__name__)


def delete_journal_ids_from_users(cr):
    try:
        cr.execute(
            """
            DELETE FROM ir_ui_view WHERE arch_db ilike '%journal_ids%' and model = 'res.users'
            """
        )
    except psycopg2.ProgrammingError:
        cr.rollback()
    return True


def migrate(cr, version):
    _logger.info("""Deleting journals from user view""")
    return delete_journal_ids_from_users(cr)
