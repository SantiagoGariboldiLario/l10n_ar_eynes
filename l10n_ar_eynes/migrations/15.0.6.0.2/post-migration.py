import logging
import psycopg2
_logger = logging.getLogger(__name__)


def update_res_users_journals(cr):
    try:
        cr.execute("""
            INSERT INTO users_journals_rel
            (user_id, journal_id)
            (SELECT user_id, journal_id FROM user_journal_rel)
        """)
    except psycopg2.ProgrammingError:
        cr.rollback()
    return True


def migrate(cr, version):
    _logger.info("""Updating m2m""")
    return update_res_users_journals(cr)
