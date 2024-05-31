import logging

import psycopg2

_logger = logging.getLogger(__name__)


def change_shipping_number_data_type(cr):
    try:
        cr.execute(
            """
                ALTER TABLE stock_picking ALTER shipping_number
                    SET DATA TYPE varchar USING CAST(shipping_number AS varchar);
            """
        )
        cr.commit()  # pylint: disable=invalid-commit
    except psycopg2.ProgrammingError:
        _logger.info(
            "Error in query execution, method: change_shipping_number_data_type"
        )
        cr.rollback()
    return True


def migrate(cr, version):
    _logger.info("""Change shipping_number data type to CHAR...""")
    change_shipping_number_data_type(cr)
    return True
