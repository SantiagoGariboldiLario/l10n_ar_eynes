import logging

import psycopg2

_logger = logging.getLogger(__name__)


def set_group_type_to_tax_group(cr):
    try:
        cr.execute(
            """
                UPDATE account_tax_group
                SET "group_type" = 'vat'
                WHERE "name" = 'Vat';

                UPDATE account_tax_group
                SET "group_type" = 'retention'
                WHERE "name" = 'Retentions';

                UPDATE account_tax_group
                SET "group_type" = 'perception'
                WHERE "name" = 'Perceptions';

                UPDATE account_tax_group
                SET "group_type" = 'internals'
                WHERE "name" = 'Internal';

                UPDATE account_tax_group
                SET "group_type" = 'other'
                WHERE "name" = 'Other';
            """
        )
        cr.commit()  # pylint: disable=invalid-commit
    except psycopg2.ProgrammingError:
        _logger.info(
            "Error in query execution, method: set_group_type_to_tax_group"
        )
        cr.rollback()
    return True


def migrate(cr, version):
    _logger.info("""Set group type to account.tax.group...""")
    set_group_type_to_tax_group(cr)
    return True
