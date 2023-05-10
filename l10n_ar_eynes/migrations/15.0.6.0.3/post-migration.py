import logging

import psycopg2

_logger = logging.getLogger(__name__)


def update_issued_checks(cr):
    try:
        cr.execute(
            """
            INSERT INTO account_payment_order_issued_check_line
            (
                payment_order_id,
                journal_id,
                issued_check_id,
                checkbook_id,
                amount,
                issue_date,
                payment_date,
                clearing,
                origin,
                signatory,
                crossed,
                not_order
            )
            (
                SELECT payment_order_id,
                journal_id,
                id,
                checkbook_id,
                amount,
                issue_date,
                payment_date,
                clearing,
                origin,
                signatory,
                crossed,
                not_order
                FROM account_check
                WHERE payment_order_id is not null
                AND internal_type = 'issued'
            )
        """
        )
    except psycopg2.ProgrammingError:
        cr.rollback()
    return True


def migrate(cr, version):
    _logger.info("""Updating issued_checks""")
    return update_issued_checks(cr)
