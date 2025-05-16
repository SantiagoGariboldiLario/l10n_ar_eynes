import logging
import psycopg2

from odoo.tools.sql import drop_index

_logger = logging.getLogger(__name__)


def clear_account_move_unique_name_eynes_index(cr):
    try:
        drop_index(cr, "account_move_unique_name_eynes", "account_move")
        cr.commit()  # pylint: disable=invalid-commit
    except psycopg2.ProgrammingError:
        _logger.info(
            "Error in query execution, method: clear_account_move_unique_name_eynes_index"
        )
        cr.rollback()


def migrate(cr, version):
    _logger.info("""Deleting wrong account_move_unique_name_eynes...""")
    clear_account_move_unique_name_eynes_index(cr)
    return True
