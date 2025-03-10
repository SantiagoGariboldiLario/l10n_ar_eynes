import logging

import psycopg2

_logger = logging.getLogger(__name__)


def auto_complete_is_opening(cr):
    try:
        cr.execute(
            """
                UPDATE account_move SET is_opening = false;
            """
        )
        cr.commit()  # pylint: disable=invalid-commit
    except psycopg2.ProgrammingError:
        _logger.info(
            "Error in query execution, method: auto_complete_is_opening"
        )
        cr.rollback()


def auto_complete_is_closing(cr):
    try:
        cr.execute(
            """
                UPDATE account_move SET is_closing = false;
            """
        )
        cr.commit()  # pylint: disable=invalid-commit
    except psycopg2.ProgrammingError:
        _logger.info(
            "Error in query execution, method: auto_complete_is_closing"
        )
        cr.rollback()


def migrate(cr, version):
    _logger.info("""Set is_opening field to false...""")
    auto_complete_is_opening(cr)
    _logger.info("""Set is_closing field to false...""")
    auto_complete_is_closing(cr)
    return True
