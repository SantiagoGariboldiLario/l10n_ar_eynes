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
        cr.commit()  # pylint: disable=invalid-commit
    except psycopg2.ProgrammingError:
        _logger.info(
            "Error in query execution, method: delete_journal_ids_from_users"
        )
        cr.rollback()
    return True


def migrate(cr, version):
    _logger.info("""Deleting journals from user view""")
    return delete_journal_ids_from_users(cr)
