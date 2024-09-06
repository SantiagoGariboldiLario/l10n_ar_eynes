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

    @api.depends(
        'currency_id', 'company_id', 'move_id.date', 'move_id.currency_rate'
    )
    def _compute_currency_rate(self):
        # pylint: disable=missing-return
        super(AccountMoveLine, self)._compute_currency_rate()
        for line in self:
            if not line.is_same_currency:
                new_rate = (
                    (1 / line.move_id.currency_rate)
                    if (
                        line.move_id.currency_id.preciated
                        and line.move_id.currency_rate
                    )
                    else (line.move_id.currency_rate or line.currency_rate)
                )
                if line.currency_rate != new_rate:
                    line.currency_rate = new_rate

    @api.depends(
        'tax_ids',
        'currency_id',
        'partner_id',
        'analytic_distribution',
        'balance',
        'partner_id',
        'move_id.partner_id',
        'price_unit',
        'quantity',
    )
    def _compute_all_tax(self):
        # pylint: disable=missing-return
        super(AccountMoveLine, self)._compute_all_tax()
        product_with_perception_lines = self.filtered(
            lambda aml: aml.display_type == 'product'
            and aml.move_id.is_invoice(True)
            and 'perception' in aml.tax_ids.tax_group_id.mapped('group_type')
        )
        invoices = product_with_perception_lines.mapped('move_id')
        for inv in invoices:
            inv_product_with_perception_lines = (
                product_with_perception_lines.filtered(
                    lambda aml: aml.move_id == inv
                )
            )
            if not inv.disable_perceptions and inv.perception_ids:
                sign = -1 if inv.is_inbound() else 1
                perceptions = (
                    inv_product_with_perception_lines.tax_ids.filtered(
                        lambda tax: tax.tax_group_id.group_type == 'perception'
                    )
                )
                for perception in perceptions:
                    lines_with_perception = (
                        inv_product_with_perception_lines.filtered(
                            lambda aml: perception in aml.tax_ids
                        )
                    )
                    perception_total_base = sum(
                        inv.perception_ids.filtered(
                            lambda ptl: ptl.perception_id == perception
                        ).mapped('base')
                    )
                    perception_total_amount = sum(
                        inv.perception_ids.filtered(
                            lambda ptl: ptl.perception_id == perception
                        ).mapped('amount')
                    )
                    line_perception_base = inv.currency_id.round(
                        perception_total_base / len(lines_with_perception)
                    )
                    line_perception_amount = inv.currency_id.round(
                        perception_total_amount / len(lines_with_perception)
                    )
                    for aml in lines_with_perception:
                        rate = aml.currency_rate
                        for key in aml.compute_all_tax:
                            if (
                                aml.compute_all_tax[key].get('name', '')
                                == perception.name
                            ):
                                aml.compute_all_tax[key]['balance'] = (
                                    sign * line_perception_amount / rate
                                )
                                aml.compute_all_tax[key]['amount_currency'] = (
                                    sign * line_perception_amount
                                )
                                aml.compute_all_tax[key]['tax_base_amount'] = (
                                    line_perception_base / rate
                                )

    def _get_computed_taxes(self):
        tax_ids = super(AccountMoveLine, self)._get_computed_taxes()
        if self.move_id.is_sale_document(include_receipts=True):
            perceptions = self.env['account.tax']
            for perception in self.move_id.perception_ids.mapped(
                'perception_id'
            ):
                for perception_line in self.move_id.perception_ids.filtered(
                    lambda line: line.perception_id == perception
                ):
                    application = perception_line.tax_app_id.check_concept(
                        self.account_id
                    )
                    if application:
                        perceptions += perception
            tax_ids += perceptions
        elif (
            self.move_id.is_purchase_document(include_receipts=True)
            and self.move_id.perception_ids
        ):
            tax_ids += self.move_id.perception_ids.mapped('perception_id')
        return tax_ids

    def link_perception_to_move_lines(self):
        self._compute_tax_ids()
        self._compute_all_tax()

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
