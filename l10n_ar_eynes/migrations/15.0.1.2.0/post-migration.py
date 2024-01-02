import logging

import psycopg2

_logger = logging.getLogger(__name__)


def copy_ws_pos_relation(cr):
    try:
        cr.execute(
            """
            UPDATE ws_pos_line SET pos_id = id;
            """
        )
        cr.commit()  # pylint: disable=invalid-commit
    except psycopg2.ProgrammingError:
        _logger.info("Error in query execution, method: copy_ws_pos_relation")
        cr.rollback()
    return True


def migrate(cr, version):
    _logger.info("""Copying WSFE models to WS...""")
    copy_ws_pos_relation(cr)
    return True
