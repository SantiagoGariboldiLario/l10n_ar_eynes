import logging

from odoo import fields
from odoo.tests.common import Form, tagged

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
        """test for onchange_income_lines() and onchange_payment_lines() method"""

        with Form(self.receipt_order) as receipt:
            with receipt.income_line_ids.new() as line:
                line.invoice_id = self.invoice_1
            with receipt.income_line_ids.edit(0) as line:
                line.reconcile = True
        # implicit execution of onchange_income_line and amount_full_conciliation

        self.assertEqual(self.receipt_order.writeoff_amount, -1634.4)

        # implicit execution of onchange_payment_line
        with Form(self.receipt_order) as receipt:
            with receipt.payment_mode_line_ids.new() as line:
                line.payment_mode_id = self.company_data['default_journal_cash']
                line.amount = 1634.4

        self.assertEqual(self.receipt_order.writeoff_amount, 0)
        self.assertEqual(self.receipt_order.amount, 1634.4)

    def test_clean_payment_lines(self):
        """test for _clean_payment_lines() method"""

        with Form(self.receipt_order) as receipt:
            with receipt.payment_mode_line_ids.new() as line:
                line.payment_mode_id = self.company_data['default_journal_cash']
                line.name = 'Pago 1'
                line.amount = 1000

            with receipt.payment_mode_line_ids.new() as line:
                line.payment_mode_id = self.company_data['default_journal_cash']
                line.name = 'Pago 2'
                line.amount = 0

        recepit = self.receipt_order
        self.assertEqual(len(recepit.payment_mode_line_ids), 2)

        recepit._clean_payment_lines()
        self.assertEqual(len(recepit.payment_mode_line_ids), 1)
        self.assertRecordValues(
            recepit.payment_mode_line_ids,
            [
                {
                    'payment_mode_id': self.company_data[
                        'default_journal_cash'
                    ].id,
                    'name': 'Pago 1',
                    'amount': 1000,
                }
            ],
        )

    def test_proforma_voucher(self):
        """test for proforma_voucher() method"""
        with Form(self.receipt_order) as receipt:
            with receipt.income_line_ids.new() as line:
                line.invoice_id = self.invoice_1
            with receipt.income_line_ids.edit(0) as line:
                line.reconcile = True

            with receipt.payment_mode_line_ids.new() as line:
                line.payment_mode_id = self.company_data['default_journal_cash']
                line.amount = 1634.4

        receipt = self.receipt_order
        self.assertEqual(receipt.writeoff_amount, 0)
        self.assertEqual(receipt.amount, 1634.4)

        # paym ent order confirmation
        receipt.proforma_voucher()

        self.assertRecordValues(
            receipt,
            [{'state': 'posted'}],
        )
        self.assertRecordValues(
            self.invoice_1,
            [
                {
                    'state': 'posted',
                    'payment_state': 'paid',
                }
            ],
        )
        move = receipt.move_id
        self.assertNotEqual(move, False)
        self.assertEqual(move.line_ids, receipt.move_line_ids)
        self.assertEqual(
            sum(move.line_ids.mapped('debit')),
            sum(move.line_ids.mapped('credit')),
        )
