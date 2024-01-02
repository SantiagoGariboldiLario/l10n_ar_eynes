import logging

import psycopg2

_logger = logging.getLogger(__name__)


def copy_ws_pos_table(cr):
    try:
        cr.execute(
            """
            CREATE TABLE ws_pos_line
                AS TABLE ws_pos;
            """
        )
        cr.commit()  # pylint: disable=invalid-commit
    except psycopg2.ProgrammingError:
        _logger.info("Error in query execution, method: copy_ws_pos_table")
        cr.rollback()
    return True


def migrate(cr, version):
    _logger.info("""Copying WSFE models to WS...""")
    copy_ws_pos_table(cr)
    return True
