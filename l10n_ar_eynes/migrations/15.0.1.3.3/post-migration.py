import logging

import psycopg2

_logger = logging.getLogger(__name__)


def rename_fce_invoices(cr):
    try:
        cr.execute(
            """
                UPDATE account_move
                SET "name" = CONCAT('FCE', "name")
                WHERE "is_FCE_invoice" IS TRUE
                AND "move_type" = 'out_invoice'
                AND "is_debit_note" IS FALSE
                AND "state" != 'draft'
                AND "name" NOT LIKE 'FCE%';

                UPDATE account_move
                SET "name" = CONCAT('NCE', "name")
                WHERE "is_FCE_invoice" IS TRUE
                AND "move_type" = 'out_refund'
                AND "state" != 'draft'
                AND "name" NOT LIKE 'NCE%';

                UPDATE account_move
                SET "name" = CONCAT('NDE', "name")
                WHERE "is_FCE_invoice" IS TRUE
                AND "move_type" = 'out_invoice'
                AND "is_debit_note" IS TRUE
                AND "state" != 'draft'
                AND "name" NOT LIKE 'NDE%';
            """
        )
        cr.commit()  # pylint: disable=invalid-commit
    except psycopg2.ProgrammingError:
        _logger.info("Error in query execution, method: rename_fce_invoices")
        cr.rollback()
    return True


def migrate(cr, version):
    _logger.info("""Rename FCE, NCE, NDE invoices...""")
    rename_fce_invoices(cr)
    return True
