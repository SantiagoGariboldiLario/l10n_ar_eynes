import logging

from odoo import fields
from odoo.tests.common import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

_logger = logging.getLogger(__name__)


@tagged('post_install', '-at_install')
class TestLocAr(AccountTestInvoicingCommon):
    """Set up for localization tests"""

    @classmethod
    def setUpClass(cls, chart_template_ref=None):
        super().setUpClass(chart_template_ref=chart_template_ref)

        cls.company_data['company'].write(
            {
                'parent_id': cls.env.ref('base.main_company').id,
                'currency_id': cls.env.ref('base.ARS').id,
            }
        )

        cls.company_data['default_journal_sale'].write(
            {
                'due_date': fields.Date.to_date('2023-01-01'),
            }
        )
