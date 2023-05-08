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
        date = invoice._get_currency_rate_date() or fields.Date.today()
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

        date = self.invoice_id._get_currency_rate_date() or fields.Date.today()
        company = self.env.user.company_id
        curr_rate = self.new_currency_id._get_currency_rate(company, date)
        if self.new_currency_id.preciated:
            self.new_currency_rate = curr_rate.rate_preciated
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

        actual_rate = self.actual_currency_rate
        new_rate = self.new_currency_rate
        if actual_rate and new_rate:
            date = invoice._get_currency_rate_date() or fields.Date.today()
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

        for line in invoice.invoice_line_ids:
            line.price_unit *= rate

        # Recalculate taxes
        invoice._onchange_invoice_line_ids()

        # Recalculate manual taxes
        for manual_tax in filter(lambda t: t.manual, invoice.tax_line_ids):
            manual_tax.base *= rate
            manual_tax.amount *= rate

        # Recalculo en percepcion
        # try:
        #     perceptions = invoice.perception_ids
        # except AttributeError as e:
        #     print('l10n_ar_perceptions_basic not installed: %s' % e)
        # else:
        #     for perc in perceptions:
        #         perc.base *= new_base
        #         perc.amount = new_amount

        inv_vals = {
            'currency_id': new_currency.id,
            'currency_rate': new_rate,
            'secondary_currency_id': inv_currency.id,
            'secondary_currency_rate': actual_rate,
            'is_multi_currency': new_currency == company_currency,
            # 'currency_converted': True,
        }
        invoice.write(inv_vals)

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
