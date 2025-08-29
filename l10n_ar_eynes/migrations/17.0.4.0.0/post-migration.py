import logging
import psycopg2

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def change_sequence_type_to_no_gap(cr):
    env = api.Environment(cr, SUPERUSER_ID, {})
    journals = env['account.journal'].search(
        [
            ('type', 'in', ['receipt', 'payment', 'retentions', 'perceptions']),
        ]
    )
    for journal in journals:
        if journal.sequence_id.implementation != 'no_gap':
            _logger.info(
                "Changing sequence type for journal '%s' to 'no_gap'.",
                journal.name,
            )
            next_number = journal.sequence_number_next
            journal.sequence_id.write(
                {
                    'implementation': 'no_gap',
                    'number_next_actual': next_number,
                }
            )
        else:
            _logger.info(
                "Journal '%s' already has 'no_gap' sequence type.", journal.name
            )


def set_posted_before_false_on_old_apos(cr):
    try:
        cr.execute(
            """
                UPDATE account_payment_order SET posted_before = false WHERE state != 'posted';
            """
        )
        cr.commit()  # pylint: disable=invalid-commit
    except psycopg2.ProgrammingError:
        _logger.info(
            "Error in query execution, method: set_posted_before_false_on_old_apos SET FALSE"
        )
        cr.rollback()


def set_posted_before_true_on_old_apos(cr):
    try:
        cr.execute(
            """
                UPDATE account_payment_order SET posted_before = true WHERE state = 'posted';
            """
        )
        cr.commit()  # pylint: disable=invalid-commit
    except psycopg2.ProgrammingError:
        _logger.info(
            "Error in query execution, method: set_posted_before_true_on_old_apos SET TRUE"
        )
        cr.rollback()


def migrate(cr, version):
    _logger.info("""Change Journal Sequence to 'no gap'...""")
    change_sequence_type_to_no_gap(cr)
    _logger.info(
        """Set new field 'posted_before' on old account.payment.order records..."""
    )
    set_posted_before_false_on_old_apos(cr)
    set_posted_before_true_on_old_apos(cr)
    return True
