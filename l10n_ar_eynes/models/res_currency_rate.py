##############################################################################
#
#   Copyright (c) 2022-2023 Eynes SRL  (Eynes - Ingenieria del software)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
#
##############################################################################

import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class ResCurrencyRate(models.Model):
    _inherit = 'res.currency.rate'

    preciated = fields.Boolean(
        related='currency_id.preciated',
        string="Preciated",
        readonly=True,
        default=lambda self: self.env['res.currency']
        .browse(self._context.get('active_id'))
        .preciated,
    )
    rate = fields.Float(digits=(12, 8))
    rate_preciated = fields.Float(
        'Rate Preciated',
        digits=(12, 8),
        default=1.0,
        help='The rate of the currency to the currency of rate 1',
    )

    # CRUD Methods
    @api.model
    def create(self, vals):
        rate = vals.get('rate', False)
        rate_preciated = vals.get('rate_preciated', False)

        if rate is False and rate_preciated is False:
            return super(ResCurrencyRate, self).create(vals)

        default_currency = (
            self._context.get('default_currency_id')
            or vals.get('currency_id')
            or False
        )
        currency = self.env['res.currency'].browse(default_currency)
        if not currency:
            return super(ResCurrencyRate, self).create(vals)

        preciated = currency.preciated

        if preciated and rate_preciated:
            vals['rate'] = 1.0 / rate_preciated
        elif not preciated and rate:
            vals['rate_preciated'] = 1.0 / rate
        else:
            raise ValidationError(
                _(
                    'The rates are zero or is preciated and you write '
                    'in field "rate" instead of "rate preciated" '
                    'or viceversa'
                )
            )

        return super(ResCurrencyRate, self).create(vals)

    def write(self, vals):
        rate = vals.get('rate', False)
        rate_preciated = vals.get('rate_preciated', False)

        if rate is False and rate_preciated is False:
            return super(ResCurrencyRate, self).write(vals)

        for curr_rate in self:
            if curr_rate.preciated and rate_preciated:
                vals['rate'] = 1.0 / rate_preciated
            elif not curr_rate.preciated and rate:
                vals['rate_preciated'] = 1.0 / rate
            else:
                raise ValidationError(
                    _(
                        'The rates are zero or is preciated and you write '
                        'in field "rate" instead of "rate preciated" '
                        'or viceversa'
                    )
                )

        return super(ResCurrencyRate, self).write(vals)
