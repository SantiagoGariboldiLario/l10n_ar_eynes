import logging

import psycopg2

from odoo import SUPERUSER_ID, api

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


def change_account_payment_method_ref(cr):
    env = api.Environment(cr, SUPERUSER_ID, {})
    old = env.ref('account_check_printing.account_payment_method_check')
    new = env.ref('l10n_ar_eynes.account_payment_method_check')
    recs_to_change = env['account.payment.method.line'].search(
        [
            ('payment_method_id', '=', old.id),
        ]
    )
    recs_to_change.update(
        {
            'payment_method_id': new.id,
        }
    )
    return True


def migrate(cr, version):
    _logger.info("""Set group type to account.tax.group...""")
    set_group_type_to_tax_group(cr)
    _logger.info(
        """Change account_check_printing.account_payment_method_check to l10n_ar_eynes.account_payment_method_check..."""
    )
    change_account_payment_method_ref(cr)
    return True
