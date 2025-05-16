import logging
import psycopg2

from odoo.tools.sql import drop_index

_logger = logging.getLogger(__name__)


def clear_account_move_unique_name_index(cr):
    try:
        drop_index(cr, "account_move_unique_name", "account_move")
        cr.commit()  # pylint: disable=invalid-commit
    except psycopg2.ProgrammingError:
        _logger.info(
            "Error in query execution, method: clear_account_move_unique_name_index"
        )
        cr.rollback()


def new_account_move_unique_name_index(cr):
    try:
        cr.execute(
            """
            CREATE UNIQUE INDEX account_move_unique_name
            ON account_move(name, journal_id)
            WHERE (state = 'posted' AND name != '/' AND move_type = 'entry');
            """
        )
        cr.commit()  # pylint: disable=invalid-commit
    except psycopg2.ProgrammingError:
        _logger.info(
            "Error in query execution, method: new_account_move_unique_name_index"
        )
        cr.rollback()


def new_account_move_unique_name_customers_index(cr):
    try:
        cr.execute(
            """
            CREATE UNIQUE INDEX account_move_unique_name_customers
            ON account_move(name, journal_id, move_type, is_debit_note)
            WHERE (
                state = 'posted' AND name != '/'
                AND move_type IN ('out_invoice', 'out_refund', 'out_receipt')
            );
            """
        )
        cr.commit()  # pylint: disable=invalid-commit
    except psycopg2.ProgrammingError:
        _logger.info(
            "Error in query execution, method: new_account_move_unique_name_customers_index"
        )
        cr.rollback()


def new_account_move_unique_name_suppliers_index(cr):
    try:
        cr.execute(
            """
            CREATE UNIQUE INDEX account_move_unique_name_suppliers
            ON account_move(name, partner_id, journal_id, move_type, is_debit_note)
            WHERE (
                state = 'posted' AND name != '/'
                AND move_type IN ('in_invoice', 'in_refund', 'in_receipt')
            );
            """
        )
        cr.commit()  # pylint: disable=invalid-commit
    except psycopg2.ProgrammingError:
        _logger.info(
            "Error in query execution, method: new_account_move_unique_name_suppliers_index"
        )
        cr.rollback()


def migrate(cr, version):
    _logger.info("""Deleting wrong account_move_unique_name...""")
    clear_account_move_unique_name_index(cr)
    _logger.info("""Creating new account_move_unique_name...""")
    new_account_move_unique_name_index(cr)
    _logger.info("""Creating new account_move_unique_name_customers...""")
    new_account_move_unique_name_customers_index(cr)
    _logger.info("""Creating new account_move_unique_name_suppliers...""")
    new_account_move_unique_name_suppliers_index(cr)
    return True
