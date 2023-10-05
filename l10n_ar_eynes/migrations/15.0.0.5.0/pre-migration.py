import logging

import psycopg2

_logger = logging.getLogger(__name__)


def fix_old_fields(cr):
    try:
        cr.execute(
            """
            UPDATE ir_model_data SET name = 'iibb_san_juan_retentions_s'
                WHERE name = 'iibb_san_juanperceptions_s';

            UPDATE ir_model_data SET name = 'iibb_san_juan_retentions_e'
                WHERE name = 'iibb_san_juanperceptions_e';

            """
        )
    except psycopg2.ProgrammingError:
        cr.rollback()
    return True


def rename_journal_codes(cr):
    try:
        cr.execute(
            """
            UPDATE ir_model_data SET module = 'l10n_ar_eynes'
                WHERE module = 'l10n_ar_padron_ws_consumer' AND
                model = 'account.tax';

            UPDATE ir_model_data SET module = 'l10n_ar_eynes'
                WHERE module = 'l10n_ar_padron_ws_consumer' AND
                model = 'account.journal';

            """
        )

    except psycopg2.ProgrammingError:
        cr.rollback()
    return True


def migrate(cr, version):
    _logger.info("""Rename journals code to avoid duplicates""")
    fix_old_fields(cr)
    rename_journal_codes(cr)
    return True
