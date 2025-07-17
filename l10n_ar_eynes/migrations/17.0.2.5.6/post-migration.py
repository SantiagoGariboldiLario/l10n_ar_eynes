import logging
import psycopg2

_logger = logging.getLogger(__name__)


def clean_line_break_on_ret_concepts(cr):
    try:
        cr.execute(
            """
                UPDATE retention_concept
                SET name = regexp_replace(name, E'(^[\\n\\r]+)|([\\n\\r]+$)', '', 'g' );
            """
        )
        cr.commit()  # pylint: disable=invalid-commit
    except psycopg2.ProgrammingError:
        _logger.info(
            "Error in query execution, method: clean_line_break_on_ret_concepts"
        )
        cr.rollback()


def migrate(cr, version):
    _logger.info("""Clean line break on retention concepts...""")
    clean_line_break_on_ret_concepts(cr)
    return True
