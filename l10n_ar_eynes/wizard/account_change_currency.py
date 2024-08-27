###############################################################################
#   Copyright (c) 2020 Eynes S.R.L (Leandro Martinek)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
###############################################################################

import logging

from odoo import _, api, exceptions, fields, models

# from odoo.exceptions import except_orm
# from odoo.addons.decimal_precision import decimal_precision as dp
# from odoo.tools import DEFAULT_SERVER_DATE_FORMAT, \
#         DEFAULT_SERVER_DATETIME_FORMAT, float_compare

_logger = logging.getLogger(__name__)


class AccountChangeCurrency(models.TransientModel):
    _name = 'account.change.currency'
    _description = 'Change Currency'

    @api.model
    def _get_actual_currency_id(self):
        invoice_id = self._context.get('active_id', False)
        if not invoice_id:
            return False

        invoice = self.env['account.move'].browse(invoice_id)
        return invoice.currency_id

    @api.model
    def _get_actual_currency_rate(self):
        invoice_id = self._context.get('active_id', False)
        if not invoice_id:
            return False

        company = self.env.user.company_id
        invoice = self.env['account.move'].browse(invoice_id)
        date = invoice.date or fields.Date.today()
        curr_rate = invoice.currency_id._get_currency_rate(company, date)
        if invoice.currency_id.preciated:
            rate = curr_rate.preciated
        else:
            rate = curr_rate.rate

        return invoice.currency_rate or rate

    actual_currency_id = fields.Many2one(
        'res.currency',
        string="Actual Currency",
        default=_get_actual_currency_id,
        readonly=True,
    )
    actual_currency_preciated = fields.Boolean(
        related='actual_currency_id.preciated',
        string="Actual Currency Preciated",
        readonly=True,
    )
    actual_currency_rate = fields.Float(
        digits=(12, 8),
        string="Actual Currency Rate",
        default=_get_actual_currency_rate,
        readonly=True,
    )
    new_currency_id = fields.Many2one('res.currency', string="New Currency")
    new_currency_preciated = fields.Boolean(
        related='new_currency_id.preciated',
        string="New Currency Preciated",
        readonly=True,
    )
    new_currency_rate = fields.Float(digits=(12, 8), string="New Currency Rate")
    invoice_id = fields.Many2one(
        'account.move',
        string="Actual Invoice",
        default=lambda s: s._context.get('active_id', False),
    )

    @api.onchange('new_currency_id')
    def onchange_new_currency_id(self):
        if not self.new_currency_id:
            return

        date = self.invoice_id.date or fields.Date.today()
        company = self.env.user.company_id
        curr_rate = self.new_currency_id._get_currency_rate(company, date)
        if self.new_currency_id == company.currency_id:
            self.new_currency_rate = 1.0
        elif self.new_currency_id.preciated:
            self.new_currency_rate = curr_rate.inverse_company_rate
        else:
            self.new_currency_rate = curr_rate.rate

    def change_currency(self):
        cur_obj = self.env.get('res.currency')
        obj_inv = self.env.get('account.move')
        invoice = obj_inv.browse(self._context['active_id'])

        company = invoice.company_id
        company_currency = company.currency_id
        inv_currency = self.actual_currency_id
        new_currency = self.new_currency_id

        if inv_currency == new_currency:
            return {}

        amount_cur_mult = 1 if invoice.move_type.startswith("in_") else -1
        actual_rate = self.actual_currency_rate
        new_rate = self.new_currency_rate
        if actual_rate and new_rate:
            date = invoice.date or fields.Date.today()
            modify_cur_obj = cur_obj.with_context(
                currency1=(inv_currency, actual_rate),
                currency2=(new_currency, new_rate),
            )
            rate = modify_cur_obj._get_conversion_rate(
                inv_currency, new_currency, company, date
            )

        else:
            raise exceptions.ValidationError(
                _("Error!\n'actual rate' or 'new rate' not provided")
            )

        AccountMoveLine = self.env['account.move.line']
        new_invoice_lines = []
        for line in invoice.line_ids:
            line_copy = {
                'move_id': line.move_id.id,
                'account_id': line.account_id.id,
                'name': line.name,
                'quantity': line.quantity,
                'price_unit': line.price_unit * rate,
                'discount': line.discount,
                'debit': line.debit,
                'credit': line.credit,
                'balance': line.balance,
                'price_subtotal': line.price_subtotal * rate,
                'amount_currency': line.price_subtotal * rate * amount_cur_mult,
                'price_total': line.price_total * rate,
                'currency_id': new_currency.id,
                'blocked': line.blocked,
                'date_maturity': line.date_maturity,
                'partner_id': line.partner_id.id,
                'product_uom_id': line.product_uom_id.id,
                'product_id': line.product_id.id,
                'reconcile_model_id': line.reconcile_model_id.id,
                'payment_id': line.payment_id.id,
                'statement_line_id': line.statement_line_id.id,
                'tax_ids': line.tax_ids.ids,
                'tax_line_id': line.tax_line_id.id,
                'tax_base_amount': line.tax_base_amount,
                'tax_repartition_line_id': line.tax_repartition_line_id.id,
                'full_reconcile_id': line.full_reconcile_id.id,
                'sale_line_ids': line.sale_line_ids,
                # 'matched_debit_ids': ,
                # 'matched_credit_ids': ,
                # 'analytic_line_ids': ,
                'recompute_tax_line': line.recompute_tax_line,
                'display_type': line.display_type,
                'is_rounding_line': line.is_rounding_line,
                'exclude_from_invoice_tab': line.exclude_from_invoice_tab,
            }
            new_invoice_lines.append(line_copy)
        invoice.line_ids.unlink()

        inv_vals = {
            'currency_id': new_currency.id,
            'currency_rate': new_rate,
            'is_multi_currency': new_currency != company_currency,
        }
        invoice.write(inv_vals)
        invoice.invoice_line_ids = AccountMoveLine.create(new_invoice_lines)
        for perception_line in invoice.perception_ids:
            perception_line.base *= rate
            perception_line.amount *= rate

        # Mensaje de pesificacion
        msg = _(
            "Invoice currency change %(inv_curr)s => %(new_curr)s. "
            "Rate: %(curr_rate)f",
            inv_curr=inv_currency.name,
            new_curr=new_currency.name,
            curr_rate=new_rate,
        )

        invoice.message_post(body=msg)
        return {'type': 'ir.actions.act_window_close'}
