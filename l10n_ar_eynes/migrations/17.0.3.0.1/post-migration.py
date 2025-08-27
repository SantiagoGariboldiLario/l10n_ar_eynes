import logging
import psycopg2

_logger = logging.getLogger(__name__)


def _set_chart_template(cr):
    try:
        cr.execute(
            """
            UPDATE res_company SET chart_template = 'ar_eynes'
            """
        )
        cr.commit()  # pylint: disable=invalid-commit
    except psycopg2.ProgrammingError:
        _logger.info("Error in query execution, method: _set_chart_template")
        cr.rollback()


def migrate(cr, version):
    _logger.info("Seteado chart template 'ar_eynes' en compañías...")
    _set_chart_template(cr)
