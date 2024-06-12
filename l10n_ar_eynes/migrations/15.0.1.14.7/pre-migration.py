import logging

import psycopg2

_logger = logging.getLogger(__name__)


def change_issued_check_states(cr):
    try:
        cr.execute(
            """
                UPDATE account_check SET issued_check_state = 'debited'
                    WHERE issued_check_state = 'paid';
            """
        )
        cr.commit()  # pylint: disable=invalid-commit
    except psycopg2.ProgrammingError:
        _logger.info(
            "Error in query execution, method: change_issued_check_states ('Paid' to 'Debited')"
        )
        cr.rollback()

    try:
        cr.execute(
            """
                UPDATE account_check SET issued_check_state = 'waiting_debit'
                    WHERE issued_check_state = 'waiting_debit';
            """
        )
        cr.commit()  # pylint: disable=invalid-commit
    except psycopg2.ProgrammingError:
        _logger.info(
            "Error in query execution, method: change_issued_check_states ('Waiting Accreditation' to 'Waiting Debit')"
        )
        cr.rollback()
    return True


def change_third_party_check_states(cr):
    try:
        cr.execute(
            """
                UPDATE account_check SET third_party_check_state = 'expired'
                    WHERE issued_check_state = 'returned';
            """
        )
        cr.commit()  # pylint: disable=invalid-commit
    except psycopg2.ProgrammingError:
        _logger.info(
            "Error in query execution, method: change_issued_check_states ('Returned' to 'Expired')"
        )
        cr.rollback()


def migrate(cr, version):
    _logger.info("""Change issued check states...""")
    change_issued_check_states(cr)
    _logger.info("""Change third party states...""")
    change_third_party_check_states(cr)
    return True
