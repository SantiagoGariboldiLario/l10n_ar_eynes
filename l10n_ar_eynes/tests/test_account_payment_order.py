import logging

from odoo import fields
from odoo.tests.common import tagged

from .common import TestLocAr

_logger = logging.getLogger(__name__)


@tagged('post_install', '-at_install')
class TestAccountPaymentOrder(TestLocAr):
    """Account payment order tests"""

    @classmethod
    def setUpClass(cls, chart_template_ref=None):
        super().setUpClass(chart_template_ref=chart_template_ref)
        PaymentOrder = cls.env['account.payment.order']
        AccountJournal = cls.env['account.journal']

        cls.receipt_journal = AccountJournal.create(
            {
                'name': 'Receipt Test journal',
                'type': 'receipt',
                'code': 'REC01',
                'company_id': cls.env.user.company_id.id,
                'currency_id': cls.env.ref('base.ARS').id,
                'due_date': fields.Date.to_date('2023-01-01'),
                'default_account_id': cls.company_data[
                    'default_account_revenue'
                ].id,
            }
        )

        cls.payment_journal = AccountJournal.create(
            {
                'name': 'Payment Test journal',
                'type': 'payment',
                'code': 'PAY02',
                'company_id': cls.env.user.company_id.id,
                'currency_id': cls.env.ref('base.ARS').id,
                'due_date': fields.Date.to_date('2023-01-01'),
                'default_account_id': cls.company_data[
                    'default_account_expense'
                ].id,
            }
        )

        cls.payment_order = PaymentOrder.create(
            {
                'partner_id': cls.partner_a.id,
                'journal_id': cls.payment_journal.id,
                'type': 'payment',
                'company_id': cls.env.user.company_id.id,
                'date': fields.Date.today(),
            }
        )

        cls.receipt_order = PaymentOrder.create(
            {
                'partner_id': cls.partner_b.id,
                'journal_id': cls.receipt_journal.id,
                'type': 'receipt',
                'company_id': cls.env.user.company_id.id,
                'date': fields.Date.today(),
            }
        )

        cls.invoice_1 = cls.env['account.move'].create(
            {
                'move_type': 'out_invoice',
                'partner_id': cls.partner_b.id,
                'date': fields.Date.today(),
                'invoice_date': fields.Date.today(),
                'currency_id': cls.env.ref('base.ARS').id,
                'journal_id': cls.company_data['default_journal_sale'].id,
                'denomination': 'e',
                'local': True,
                'invoice_line_ids': [
                    (
                        0,
                        0,
                        {
                            'product_id': cls.product_a.id,
                            'quantity': 800.0,
                            'name': 'product test 1',
                            'discount': 10.00,
                            'price_unit': 2.27,
                        },
                    )
                ],
            }
        )
        cls.invoice_1.action_post()

    def test_gather_income_lines(self):
        """test for gather_income_lines() method"""
        self.receipt_order.gather_income_lines()

        self.assertRecordValues(
            self.receipt_order.income_line_ids,
            [
                {
                    'payment_order_id': self.receipt_order.id,
                    'invoice_id': self.invoice_1.id,
                    'amount_original': self.invoice_1.amount_total,
                },
            ],
        )

    def test_onchange_income_lines(self):
        self.invoice_1.action_post()

        self.receipt_order.income_line_ids = [
            (0, 0, {'invoice_id': self.invoice_1.id})
        ]

        self.receipt_order.onchange_income_lines()
        self.receipt_order.income_line_ids[0].update({'reconcile': True})
        self.receipt_order.income_line_ids[0].amount_full_conciliation()
        self.receipt_order.onchange_income_lines()
        self.assertEqual(self.receipt_order.writeoff_amount, -1634.4)

        cash_journal = self.env['account.journal'].search(
            [('code', '=', 'CSH1')], limit=1
        )
        self.receipt_order.payment_mode_line_ids = [
            (
                0,
                0,
                {
                    'payment_mode_id': cash_journal.id,
                    'amount': 1634.4,
                },
            )
        ]
        self.receipt_order.onchange_payment_line()
        self.assertEqual(self.receipt_order.writeoff_amount, 0)
        self.assertEqual(self.receipt_order.amount, 1634.4)
