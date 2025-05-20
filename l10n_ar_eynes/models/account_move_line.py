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
            if inv.perception_ids:
                sign = -1 if inv.is_inbound() else 1
                perceptions = (
                    inv_product_with_perception_lines.tax_ids.filtered(
                        lambda tax: tax.tax_group_id.group_type == 'perception'
                    )
                )
                for perception in perceptions:
                    perception = perception._origin
                    lines_with_perception = (
                        inv_product_with_perception_lines.filtered(
                            lambda aml: perception in aml.tax_ids._origin
                        )
                    )
                    perception_total_base = line_perception_base = 0.0
                    perception_total_amount = line_perception_amount = 0.0
                    if lines_with_perception:
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

        product_lines = self.filtered(
            lambda aml: aml.display_type == 'product'
            and aml.move_id.is_invoice(True)
        )
        invoices = product_lines.mapped('move_id').filtered(
            lambda inv: inv.is_purchase_document()
        )
        for inv in invoices:
            inv_product_with_internal_taxes_lines = product_lines.filtered(
                lambda aml: aml.move_id == inv
            )
            if inv.is_purchase_document() and inv.internal_taxes_ids:
                sign = -1 if inv.is_inbound() else 1
                internals = (
                    inv_product_with_internal_taxes_lines.tax_ids.filtered(
                        lambda tax: tax.tax_group_id.group_type == 'internals'
                    )
                )
                for internal_tax in internals:
                    internal_tax = internal_tax._origin
                    lines_with_internals = (
                        inv_product_with_internal_taxes_lines.filtered(
                            lambda aml: internal_tax in aml.tax_ids._origin
                        )
                    )
                    internal_tax_total_base = line_internal_tax_base = 0.0
                    internal_tax_total_amount = line_internal_tax_amount = 0.0
                    if lines_with_internals:
                        internal_tax_total_base = sum(
                            inv.internal_taxes_ids.filtered(
                                lambda ptl: ptl.tax_id == internal_tax
                            ).mapped('base')
                        )
                        internal_tax_total_amount = sum(
                            inv.internal_taxes_ids.filtered(
                                lambda ptl: ptl.tax_id == internal_tax
                            ).mapped('amount')
                        )
                        line_internal_tax_base = inv.currency_id.round(
                            internal_tax_total_base / len(lines_with_internals)
                        )
                        line_internal_tax_amount = inv.currency_id.round(
                            internal_tax_total_amount
                            / len(lines_with_internals)
                        )
                    for aml in lines_with_internals:
                        rate = aml.currency_rate
                        for key in aml.compute_all_tax:
                            if (
                                aml.compute_all_tax[key].get('name', '')
                                == internal_tax.name
                            ):
                                aml.compute_all_tax[key]['balance'] = (
                                    sign * line_internal_tax_amount / rate
                                )
                                aml.compute_all_tax[key]['amount_currency'] = (
                                    sign * line_internal_tax_amount
                                )
                                aml.compute_all_tax[key]['tax_base_amount'] = (
                                    line_internal_tax_base / rate
                                )

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
        self._compute_all_tax()

    def force_compute_tax_ids(self):
        # pylint: disable=missing-return
        super(AccountMoveLine, self)._compute_tax_ids()

    def _get_computed_taxes(self):
        tax_ids = super(AccountMoveLine, self)._get_computed_taxes()

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
