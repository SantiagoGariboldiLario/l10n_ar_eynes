import logging

import psycopg2

_logger = logging.getLogger(__name__)


def remove_old_constraint(cr):
    try:
        cr.execute(
            """
                ALTER TABLE res_partner_retention
                DROP CONSTRAINT res_partner_retention_retention_partner_unique;;
            """
        )
        cr.commit()  # pylint: disable=invalid-commit
    except psycopg2.ProgrammingError:
        _logger.info("Error in query execution, method: remove_old_constraint")
        cr.rollback()
    return True


def migrate(cr, version):
    _logger.info("""Remove old constraint""")
    remove_old_constraint(cr)
    return True
