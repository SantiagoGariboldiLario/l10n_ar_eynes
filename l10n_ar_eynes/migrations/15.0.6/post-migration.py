import logging
import psycopg2
_logger = logging.getLogger(__name__)


def update_journal_fiscal_position(cr):
    try:
        cr.execute("""
            INSERT INTO journal_fiscal_position_rel
            (journal_id, fiscal_position_id)
            (SELECT id, fiscal_position_id FROM account_journal where fiscal_position_id is not null)
        """)
    except psycopg2.ProgrammingError:
        cr.rollback()
    return True


def migrate(cr, version):
    print("Yendo a migrar los datos")
    _logger.info("""Updating m2m""")
    return update_journal_fiscal_position(cr)
