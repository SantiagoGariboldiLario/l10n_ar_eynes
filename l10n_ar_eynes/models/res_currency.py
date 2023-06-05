##############################################################################
#
#   Copyright (c) 2022-2023 Eynes SRL  (Eynes - Ingenieria del software)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
#
##############################################################################

import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class ResCurrency(models.Model):
    _inherit = "res.currency"

    preciated = fields.Boolean('Currency preciated', default=False)

    def _get_conversion_rate(self, from_currency, to_currency, company, date):
        # Creo que esto del voucher esta deprecado, se utiliza otro metodo para
        # hacer las conversiones en el voucher, revisar.

        # vsc_rate = self._context.get('voucher_special_currency_rate')
        # vsc_cid = self._context.get('voucher_special_currency')

        # if vsc_rate and vsc_cid == to_currency.id:
        #     return vsc_rate

        # Give custom rate for currencies. If a currency is preciated
        # the rate will be assumed to be preciated
        currency1, rate1 = self._context.get('currency1', (False, False))
        currency2, rate2 = self._context.get('currency2', (False, False))

        if currency1 and rate1 and currency2 and rate2:
            if currency1.preciated:
                rate1 = 1 / rate1
            if currency2.preciated:
                rate2 = 1 / rate2
            if currency1 == from_currency and currency2 == to_currency:
                return rate2 / rate1
            elif currency2 == from_currency and currency1 == to_currency:
                return rate1 / rate2

        res = super(ResCurrency, self)._get_conversion_rate(
            from_currency, to_currency, company, date
        )
        return res

    def _get_currency_rate(self, company, date):
        self.ensure_one()
        domain = [
            ('currency_id', '=', self.id),
            ('name', '<=', date),
            ('company_id', '=?', company.id),
        ]
        rate_id = self.env['res.currency.rate'].search(
            domain, limit=1, order='company_id, name DESC'
        )
        return rate_id

    def _convert(self, from_amount, to_currency, company, date, _round=True):
        res = super()._convert(
            from_amount, to_currency, company, date, round=_round
        )
        if self._context.get('currency_rate'):
            old_rate = 1 / self._get_conversion_rate(
                self, to_currency, company, date
            )
            new_rate = self._context.get('currency_rate')
            res = res * (old_rate / new_rate)
        if self._context.get('inverse_currency_rate') or self._context.get(
            'from_taxes'
        ):
            old_rate = self._get_conversion_rate(
                self, to_currency, company, date
            )
            new_rate = self._context.get('inverse_currency_rate')
            res = res * (new_rate / old_rate)

        return to_currency.round(res)
