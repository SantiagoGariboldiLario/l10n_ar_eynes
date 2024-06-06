import logging

import psycopg2

_logger = logging.getLogger(__name__)


def change_country_cuit_code_data_type(cr):
    try:
        cr.execute(
            """
                ALTER TABLE dst_cuit_codes ALTER code
                    SET DATA TYPE varchar USING CAST(code AS varchar);
            """
        )
        cr.commit()  # pylint: disable=invalid-commit
    except psycopg2.ProgrammingError:
        _logger.info(
            "Error in query execution, method: change_country_cuit_code_data_type"
        )
        cr.rollback()
    return True


def migrate(cr, version):
    _logger.info("""Change dst_cuit_codes column code data type to CHAR...""")
    change_country_cuit_code_data_type(cr)
    return True
