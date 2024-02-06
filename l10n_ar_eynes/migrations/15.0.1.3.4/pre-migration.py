import logging
import psycopg2

_logger = logging.getLogger(__name__)

def move_rejected_issued_checks_journal_id(cr):
    try:
        cr.execute(
            """
            UPDATE account_check_config acc
            SET rejected_issued_checks_journal_id = rcs.rejected_issued_checks_journal_id
            FROM res_config_settings rcs
            WHERE acc.id = rcs.id
            """
        )
        cr.commit()
    except psycopg2.ProgrammingError:
        _logger.info("Error in query execution, method: move_rejected_issued_checks_journal_id")
        cr.rollback()
    return True

def migrate(cr, version):
    _logger.info("""Moving 'rejected_issued_checks_journal_id' from 'res.config.settings' to 'account.check.config'...""")
    move_rejected_issued_checks_journal_id(cr)
    return True
