import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    issued_check_id = fields.Many2one(
        comodel_name='account.check',
        string='Issued Check',
        domain=[('internal_type', '=', 'issued')],
    )
    counterpart = fields.Char(
        "Counterpart",
        compute='_compute_counterpart',
        help="Compute the counter part accounts of "
        "this journal item for this journal entry. This can be needed in reports.",
    )

    @api.depends('move_id.line_ids')
    def _compute_counterpart(self):
        for rec in self:
            counterpart = set()
            for line in rec.move_id.line_ids:
                if line.account_id.code != rec.account_id.code:
                    counterpart.add(line.account_id.code)
            if len(counterpart) > 2:
                counterpart = list(counterpart)[0:2] + ["..."]
            self.counterpart = ",".join(counterpart)

    def _compute_all_vat_taxes(self):
        invoice = self.move_id
        currency = invoice.currency_id.with_context(
            date=invoice.invoice_date or fields.Date.context_today(invoice)
        )
        company_currency = invoice.company_id.currency_id

        result = {}
        for line in self:
            result[line.id] = {
                'price_unit': 0.0,
                'amount_untaxed': 0.0,
                'amount_total': 0.0,
                'amount_no_taxed': 0.0,
                'amount_exempt': 0.0,
                'vat_taxes': {},
            }

            # Obtenemos los valores de la linea de factura
            line_taxes = {}
            taxes = line.tax_ids.compute_all(
                (line.price_unit * (1 - (line.discount or 0.0) / 100.0)),
                invoice.currency_id,
                line.quantity,
                line.product_id,
                invoice.partner_id,
            )

            amount_tax = 0.0
            amount_base = 0.0
            amount_exempt = 0.0
            for tax in taxes['taxes']:
                if not tax['tax_group_name'].lower() == 'vat':
                    continue

                val = {}
                val['invoice_line_id'] = line.id
                val['name'] = tax['name']
                val['amount'] = tax['amount']
                val['base'] = tax['base']
                val['base_amount'] = currency.compute(
                    val['base'], company_currency, round=False
                )
                val['tax_amount'] = currency.compute(
                    val['amount'], company_currency, round=False
                )
                val['account_id'] = tax['account_id'] or line.account_id.id
                amount_tax += tax['amount']
                if tax['is_exempt']:
                    amount_exempt += val['base']
                else:
                    amount_base += val['base']

                line_taxes[tax['id']] = val

            price = line.price_unit * (1 - (line.discount or 0.0) / 100.0)

            result[line.id]['price_unit'] = price
            result[line.id]['amount_untaxed'] = line.price_subtotal
            result[line.id]['amount_total'] = amount_tax + line.price_subtotal
            result[line.id]['amount_no_taxed'] = (
                line.price_subtotal - amount_base - amount_exempt
            )
            result[line.id]['amount_exempt'] = amount_exempt
            result[line.id]['amount_taxed'] = amount_base
            result[line.id]['vat_taxes'] = line_taxes

        return result

    def _get_computed_price_unit(self):
        modify_self = self.with_context(
            currency_rate=self.move_id.currency_rate
        )
        return super(AccountMoveLine, modify_self)._get_computed_price_unit()

    def _get_price_total_and_subtotal(
        self,
        price_unit=None,
        quantity=None,
        discount=None,
        currency=None,
        product=None,
        partner=None,
        taxes=None,
        move_type=None,
    ):
        modify_self = self.with_context(
            currency_rate=self.move_id.currency_rate
        )
        res = super(AccountMoveLine, modify_self)._get_price_total_and_subtotal(
            price_unit=price_unit,
            quantity=quantity,
            discount=discount,
            currency=currency,
            product=product,
            partner=partner,
            taxes=taxes,
            move_type=move_type,
        )
        return res

    def _get_fields_onchange_subtotal(
        self,
        price_subtotal=None,
        move_type=None,
        currency=None,
        company=None,
        date=None,
    ):
        modify_self = self.with_context(
            inverse_currency_rate=self.move_id.currency_rate
        )
        return super(
            AccountMoveLine, modify_self
        )._get_fields_onchange_subtotal(
            price_subtotal=price_subtotal,
            move_type=move_type,
            currency=currency,
            company=company,
            date=date,
        )

    def _get_fields_onchange_balance(
        self,
        quantity=None,
        discount=None,
        amount_currency=None,
        move_type=None,
        currency=None,
        taxes=None,
        price_subtotal=None,
        force_computation=False,
    ):
        modify_self = self.with_context(
            currency_rate=self.move_id.currency_rate
        )
        return super(AccountMoveLine, modify_self)._get_fields_onchange_balance(
            quantity=quantity,
            discount=discount,
            amount_currency=amount_currency,
            move_type=move_type,
            currency=currency,
            taxes=taxes,
            price_subtotal=price_subtotal,
            force_computation=force_computation,
        )

    @api.onchange('amount_currency')
    def _onchange_amount_currency(self):
        modify_self = self.with_context(
            inverse_currency_rate=self.move_id.currency_rate
        )
        return super(AccountMoveLine, modify_self)._onchange_amount_currency()

    def price_unit_to_PDF(self):
        price_unit = self.price_unit
        if self.move_id.denomination == 'b':
            tax_amount = 0
            vat_taxes = self.tax_ids.filtered(
                lambda tax: tax.tax_group_id
                and tax.tax_group_id.group_type == 'vat'
            )
            for tax in vat_taxes:
                tax_amount += price_unit * tax.amount / 100
            price_unit += tax_amount
        return price_unit

    def price_subtotal_to_PDF(self):
        price_subtotal = self.price_subtotal
        if self.move_id.denomination == 'b':
            tax_amount = 0
            vat_taxes = self.tax_ids.filtered(
                lambda tax: tax.tax_group_id
                and tax.tax_group_id.group_type == 'vat'
            )
            for tax in vat_taxes:
                tax_amount += price_subtotal * tax.amount / 100
            price_subtotal += tax_amount
        return price_subtotal

    def get_iva_tax(self):
        iva = self.env.ref('l10n_ar_eynes.vat_tax_group')
        for tax in self.tax_ids:
            if iva.id == tax.tax_group_id.id:
                return tax
        return False
