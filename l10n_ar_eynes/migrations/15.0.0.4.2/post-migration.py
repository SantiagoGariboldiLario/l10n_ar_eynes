import logging

import psycopg2

_logger = logging.getLogger(__name__)


def copy_user_journals(cr):
    try:
        cr.execute(
            """
            INSERT INTO users_journals_priority_rel
            (user_id, journal_id, priority)
            SELECT
                user_id,
                journal_id,
                ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY journal_id) as priority
            FROM
                users_journals_rel;
        """
        )
    except psycopg2.ProgrammingError:
        cr.rollback()
    return True


def migrate(cr, version):
    _logger.info("""Updating user journals""")
    return copy_user_journals(cr)
