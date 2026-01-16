import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    fiscal_credit = fields.Selection(
        [
            ('direct_taxed', 'Direct Taxed'),
            ('direct_exempt', 'Direct Exempt'),
            ('apport', 'Apport'),
        ],
        compute='_compute_fiscal_credit',
        readonly=False,
        store=True,
        copy=True,
    )
    issued_check_id = fields.Many2one(
        comodel_name='account.check',
        string='Issued Check',
        domain=[('internal_type', '=', 'issued')],
    )
    required_fiscal_credit = fields.Boolean(
        default=False, store=False, compute='_compute_required_fiscal_credit'
    )

    @api.depends('move_id.show_fiscal_credit', 'tax_ids')
    def _compute_required_fiscal_credit(self):
        for move_line in self:
            required = False
            if move_line.move_id.show_fiscal_credit:
                if move_line.tax_ids.filtered(
                    lambda tax: tax.tax_group_id.group_type == 'vat'
                ):
                    required = True
            move_line.required_fiscal_credit = required

    @api.depends('product_id')
    def _compute_fiscal_credit(self):
        for rec in self:
            fiscal_credit = rec.fiscal_credit
            if (
                rec.move_id.show_fiscal_credit
                and rec.product_id
                and not fiscal_credit
            ):
                fiscal_credit = rec.product_id.fiscal_credit
            rec.fiscal_credit = fiscal_credit

    @api.depends(
        'currency_id', 'company_id', 'move_id.date', 'move_id.currency_rate'
    )
    def _compute_currency_rate(self):
        # pylint: disable=missing-return
        super()._compute_currency_rate()
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
    def _get_line_tax_details(self):
        self.ensure_one()
        base_line = (
            self.move_id._prepare_product_base_line_for_taxes_computation(self)
        )
        self.env['account.tax']._add_tax_details_in_base_line(
            base_line, self.company_id
        )
        return base_line['tax_details']

    # @api.depends(
    #     'tax_ids',
    #     'currency_id',
    #     'partner_id',
    #     'analytic_distribution',
    #     'balance',
    #     'partner_id',
    #     'move_id.partner_id',
    #     'price_unit',
    #     'quantity',
    # )
    # def _compute_all_tax(self):
    #     # In v19 the base model no longer exposes _compute_all_tax/compute_all_tax;
    #     # guard for backward compatibility and skip if the structure is absent.
    #     compute_super = getattr(super(), "_compute_all_tax", None)
    #     if compute_super:
    #         compute_super()
    #     if not hasattr(self, "compute_all_tax"):
    #         return

    #     def _distribute_rounded_values(total_base, total_amount, lines):
    #         # Distribute rounded values and remainder to last line
    #         num_lines = len(lines)
    #         rounded_bases = []
    #         rounded_amounts = []
    #         for i, _aml in enumerate(lines):
    #             if i < num_lines - 1:
    #                 rounded_base = inv.currency_id.round(total_base / num_lines)
    #                 rounded_amount = inv.currency_id.round(
    #                     total_amount / num_lines
    #                 )
    #                 rounded_bases.append(rounded_base)
    #                 rounded_amounts.append(rounded_amount)
    #             else:
    #                 # Last line gets the remainder
    #                 rounded_base = total_base - sum(rounded_bases)
    #                 rounded_amount = total_amount - sum(rounded_amounts)
    #                 rounded_bases.append(rounded_base)
    #                 rounded_amounts.append(rounded_amount)
    #         return rounded_amounts, rounded_bases

    #     def _assign_distributed_values(
    #         lines, tax_name, sign, rounded_amounts, rounded_bases
    #     ):
    #         # Assign distributed values to lines
    #         for idx, aml in enumerate(lines):
    #             rate = aml.currency_rate
    #             for key in aml.compute_all_tax:
    #                 if aml.compute_all_tax[key].get('name', '') == tax_name:
    #                     aml.compute_all_tax[key]['balance'] = (
    #                         sign * rounded_amounts[idx] / rate
    #                     )
    #                     aml.compute_all_tax[key]['amount_currency'] = (
    #                         sign * rounded_amounts[idx]
    #                     )
    #                     aml.compute_all_tax[key]['tax_base_amount'] = (
    #                         rounded_bases[idx] / rate
    #                     )

    #     product_with_perception_lines = self.filtered(
    #         lambda aml: aml.display_type == 'product'
    #         and aml.move_id.is_invoice(True)
    #         and 'perception' in aml.tax_ids.tax_group_id.mapped('group_type')
    #     )
    #     invoices = product_with_perception_lines.mapped('move_id')
    #     for inv in invoices:
    #         inv_product_with_perception_lines = (
    #             product_with_perception_lines.filtered(
    #                 lambda aml: aml.move_id == inv
    #             )
    #         )
    #         if inv.perception_ids:
    #             sign = -1 if inv.is_inbound() else 1
    #             perceptions = (
    #                 inv_product_with_perception_lines.tax_ids.filtered(
    #                     lambda tax: tax.tax_group_id.group_type == 'perception'
    #                 )
    #             )
    #             for perception in perceptions:
    #                 perception = perception._origin
    #                 lines_with_perception = (
    #                     inv_product_with_perception_lines.filtered(
    #                         lambda aml: perception in aml.tax_ids._origin
    #                     )
    #                 )
    #                 if lines_with_perception:
    #                     perception_total_base = sum(
    #                         inv.perception_ids.filtered(
    #                             lambda ptl: ptl.perception_id == perception
    #                         ).mapped('base')
    #                     )
    #                     perception_total_amount = sum(
    #                         inv.perception_ids.filtered(
    #                             lambda ptl: ptl.perception_id == perception
    #                         ).mapped('amount')
    #                     )
    #                     (
    #                         rounded_amounts,
    #                         rounded_bases,
    #                     ) = _distribute_rounded_values(
    #                         perception_total_base,
    #                         perception_total_amount,
    #                         lines_with_perception,
    #                     )
    #                     _assign_distributed_values(
    #                         lines_with_perception,
    #                         perception.name,
    #                         sign,
    #                         rounded_amounts,
    #                         rounded_bases,
    #                     )

    #     product_lines = self.filtered(
    #         lambda aml: aml.display_type == 'product'
    #         and aml.move_id.is_invoice(True)
    #     )
    #     invoices = product_lines.mapped('move_id').filtered(
    #         lambda inv: inv.is_purchase_document()
    #     )
    #     for inv in invoices:
    #         inv_product_with_internal_taxes_lines = product_lines.filtered(
    #             lambda aml: aml.move_id == inv
    #         )
    #         if inv.is_purchase_document() and inv.internal_taxes_ids:
    #             sign = -1 if inv.is_inbound() else 1
    #             internals = (
    #                 inv_product_with_internal_taxes_lines.tax_ids.filtered(
    #                     lambda tax: tax.tax_group_id.group_type == 'internals'
    #                 )
    #             )
    #             for internal_tax in internals:
    #                 internal_tax = internal_tax._origin
    #                 lines_with_internals = (
    #                     inv_product_with_internal_taxes_lines.filtered(
    #                         lambda aml: internal_tax in aml.tax_ids._origin
    #                     )
    #                 )
    #                 if lines_with_internals:
    #                     internal_tax_total_base = sum(
    #                         inv.internal_taxes_ids.filtered(
    #                             lambda ptl: ptl.tax_id == internal_tax
    #                         ).mapped('base')
    #                     )
    #                     internal_tax_total_amount = sum(
    #                         inv.internal_taxes_ids.filtered(
    #                             lambda ptl: ptl.tax_id == internal_tax
    #                         ).mapped('amount')
    #                     )
    #                     (
    #                         rounded_amounts,
    #                         rounded_bases,
    #                     ) = _distribute_rounded_values(
    #                         internal_tax_total_base,
    #                         internal_tax_total_amount,
    #                         lines_with_internals,
    #                     )
    #                     _assign_distributed_values(
    #                         lines_with_internals,
    #                         internal_tax.name,
    #                         sign,
    #                         rounded_amounts,
    #                         rounded_bases,
    #                     )

    def _get_computed_perceptions(self):
        tax_ids = self.env['account.tax']
        if (
            self.move_id.is_sale_document(include_receipts=True)
            and not self.move_id.disable_perceptions
        ):
            perceptions = self.env['account.tax']
            for perception in self.move_id.perception_ids.mapped(
                'perception_id'
            ):
                if perception.apply_custom_code:
                    perceptions += perception
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
            or (
                self.move_id.is_sale_document(include_receipts=True)
                and self.move_id.disable_perceptions
            )
            and self.move_id.perception_ids
        ):
            tax_ids += self.move_id.perception_ids.mapped('perception_id')
        return tax_ids

    def link_perception_to_move_lines(self):
        to_clean = self.env['account.tax']
        for line in self:
            if (
                line.display_type == 'product'
                and line.product_id
                and line.tax_ids
                and line.tax_ids.filtered(
                    lambda tax: tax.tax_group_id.group_type == 'vat'
                )
            ):
                existing = line.tax_ids.filtered(
                    lambda tag: tag.tax_group_id.group_type == 'perception'
                )
                to_check = line._get_computed_perceptions()
                to_clean = self.env['account.tax']
                to_add = self.env['account.tax']
                for exists in existing:
                    if exists._origin not in to_check:
                        to_clean += exists
                for new in to_check:
                    if new not in existing._origin:
                        to_add += new
                line.tax_ids -= to_clean
                line.tax_ids += to_add

    def force_compute_tax_ids(self):
        # pylint: disable=missing-return
        super()._compute_tax_ids()

    def _get_computed_taxes(self):
        tax_ids = super()._get_computed_taxes()

        if (
            self.move_id.is_sale_document(include_receipts=True)
            and self.move_id.partner_id
            and self.product_id
            and self.product_id.manufacturer_id == self.move_id.company_id
        ):
            internal_taxes = self.move_id.partner_id.get_applicable_internals()
            tax_ids += internal_taxes

        return tax_ids

    def link_internal_taxes_to_move_lines(self, taxes):
        for line in self:
            if (
                line.display_type == 'product'
                and line.product_id
                and line.tax_ids
            ):
                existing = line.tax_ids.filtered(
                    lambda tag: tag.tax_group_id.group_type == 'internals'
                )
                to_clean = self.env['account.tax']
                to_add = self.env['account.tax']
                for exists in existing:
                    if exists._origin not in taxes:
                        to_clean += exists
                for new in taxes:
                    if new not in existing._origin:
                        to_add += new
                line.tax_ids -= to_clean
                line.tax_ids += to_add

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
        for tax in self.tax_ids:
            if tax.tax_group_id.group_type == 'vat':
                return tax
        return False
