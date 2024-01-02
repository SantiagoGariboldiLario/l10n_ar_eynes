import logging

import psycopg2

_logger = logging.getLogger(__name__)


def drop_ws_pos_line_seq_table(cr):
    try:
        cr.execute(
            """
            DROP TABLE ws_pos_line_id_seq;
            """
        )
        cr.commit()  # pylint: disable=invalid-commit
    except psycopg2.ProgrammingError:
        _logger.info(
            "Error in query execution, method: drop_ws_pos_line_seq_table"
        )
        cr.rollback()
    return True


def create_ws_pos_line_seq_table(cr):
    try:
        cr.execute(
            """
            CREATE SEQUENCE ws_pos_line_id_seq
                START WITH 1
                INCREMENT BY 1
                NO MINVALUE
                NO MAXVALUE
                CACHE 1;
            """
        )
        cr.commit()  # pylint: disable=invalid-commit
    except psycopg2.ProgrammingError:
        _logger.info(
            "Error in query execution, method: create_ws_pos_line_seq_table"
        )
        cr.rollback()
    return True


def migrate(cr, version):
    _logger.info("""Deleting wrong sequence table...""")
    drop_ws_pos_line_seq_table(cr)
    _logger.info("""Creating pos line sequence table...""")
    create_ws_pos_line_seq_table(cr)
    return True
