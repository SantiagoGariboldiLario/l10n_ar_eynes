import logging
import psycopg2

_logger = logging.getLogger(__name__)

def delete_rejected_issued_checks_journal_id(cr):
    try:
        cr.execute(
            """
            ALTER TABLE res_config_settings
            DROP COLUMN IF EXISTS rejected_issued_checks_journal_id
            """
        )
        cr.commit()
    except psycopg2.ProgrammingError:
        _logger.info("Error in query execution, method: delete_rejected_issued_checks_journal_id")
        cr.rollback()
    return True

def migrate(cr, version):
    _logger.info("""Deleting 'rejected_issued_checks_journal_id' from 'res.config.settings'...""")
    delete_rejected_issued_checks_journal_id(cr)
    return True
