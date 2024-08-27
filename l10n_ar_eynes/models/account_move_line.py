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

    @api.depends('tax_ids', 'currency_id', 'partner_id', 'analytic_distribution', 'balance', 'partner_id', 'move_id.partner_id', 'price_unit', 'quantity')
    def _compute_all_tax(self):
        # pylint: disable=missing-return
        super(AccountMoveLine, self)._compute_all_tax()
        product_with_perception_lines = self.filtered(
            lambda aml:
                aml.display_type == 'product' and aml.move_id.is_invoice(True)
                and 'perception' in aml.tax_ids.tax_group_id.mapped('group_type')
        )
        invoices = product_with_perception_lines.mapped('move_id')
        for inv in invoices:
            if not inv.disable_perceptions:
                sign = -1 if inv.is_inbound() else 1
                inv_product_with_perception_lines = product_with_perception_lines.filtered(lambda aml: aml.move_id == inv)
                perceptions = inv_product_with_perception_lines.tax_ids.filtered(lambda tax: tax.tax_group_id.group_type == 'perception')
                for perception in perceptions:
                    lines_with_perception = inv_product_with_perception_lines.filtered(lambda aml: perception in aml.tax_ids)
                    perception_total_base = sum(inv.perception_ids.filtered(lambda ptl: ptl.perception_id == perception).mapped('base'))
                    perception_total_amount = sum(inv.perception_ids.filtered(lambda ptl: ptl.perception_id == perception).mapped('amount'))
                    line_perception_base = inv.currency_id.round(perception_total_base / len(lines_with_perception))
                    line_perception_amount = inv.currency_id.round(perception_total_amount / len(lines_with_perception))
                    for aml in lines_with_perception:
                        for key in aml.compute_all_tax:
                            if aml.compute_all_tax[key].get('name', '') == perception.name:
                                aml.compute_all_tax[key]['balance'] = sign * line_perception_amount
                                aml.compute_all_tax[key]['amount_currency'] = sign * line_perception_amount
                                aml.compute_all_tax[key]['tax_base_amount'] = line_perception_base

    # def _get_computed_price_unit(self):
    #     modify_self = self.with_context(
    #         currency_rate=self.move_id.currency_rate
    #     )
    #     return super(AccountMoveLine, modify_self)._get_computed_price_unit()

    # def _get_price_total_and_subtotal(
    #     self,
    #     price_unit=None,
    #     quantity=None,
    #     discount=None,
    #     currency=None,
    #     product=None,
    #     partner=None,
    #     taxes=None,
    #     move_type=None,
    # ):
    #     modify_self = self.with_context(
    #         currency_rate=self.move_id.currency_rate
    #     )
    #     res = super(AccountMoveLine, modify_self)._get_price_total_and_subtotal(
    #         price_unit=price_unit,
    #         quantity=quantity,
    #         discount=discount,
    #         currency=currency,
    #         product=product,
    #         partner=partner,
    #         taxes=taxes,
    #         move_type=move_type,
    #     )
    #     return res

    # def _get_fields_onchange_subtotal(
    #     self,
    #     price_subtotal=None,
    #     move_type=None,
    #     currency=None,
    #     company=None,
    #     date=None,
    # ):
    #     modify_self = self.with_context(
    #         inverse_currency_rate=self.move_id.currency_rate
    #     )
    #     return super(
    #         AccountMoveLine, modify_self
    #     )._get_fields_onchange_subtotal(
    #         price_subtotal=price_subtotal,
    #         move_type=move_type,
    #         currency=currency,
    #         company=company,
    #         date=date,
    #     )

    # def _get_fields_onchange_balance(
    #     self,
    #     quantity=None,
    #     discount=None,
    #     amount_currency=None,
    #     move_type=None,
    #     currency=None,
    #     taxes=None,
    #     price_subtotal=None,
    #     force_computation=False,
    # ):
    #     modify_self = self.with_context(
    #         currency_rate=self.move_id.currency_rate
    #     )
    #     return super(AccountMoveLine, modify_self)._get_fields_onchange_balance(
    #         quantity=quantity,
    #         discount=discount,
    #         amount_currency=amount_currency,
    #         move_type=move_type,
    #         currency=currency,
    #         taxes=taxes,
    #         price_subtotal=price_subtotal,
    #         force_computation=force_computation,
    #     )

    # @api.onchange('amount_currency')
    # def _onchange_amount_currency(self):
    #     modify_self = self.with_context(
    #         inverse_currency_rate=self.move_id.currency_rate
    #     )
    #     return super(AccountMoveLine, modify_self)._onchange_amount_currency()

    @api.depends('product_id', 'product_uom_id', 'partner_id', 'move_id.invoice_date', 'move_id.disable_perceptions', 'quantity')
    def _compute_tax_ids(self):
        # pylint: disable=missing-return
        super(AccountMoveLine, self)._compute_tax_ids()

    def _get_computed_taxes(self):
        tax_ids = super(AccountMoveLine, self)._get_computed_taxes()
        if self.move_id.is_sale_document(include_receipts=True):
            perceptions_applications = perceptions = self.env['perception.tax.application']
            if self.account_id and not self.move_id.disable_perceptions:
                perceptions_applications = self.account_id.get_perceptions_applications()

            if self.partner_id:
                perceptions = self.env['account.tax']
                for application in perceptions_applications:
                    perception = application.perception_tax_id
                    if perception in self.partner_id.property_account_position_id.perception_ids:
                        perception_data = (
                            application.get_perception_data(self.partner_id, self.move_id.invoice_date)
                        )
                        applicable = application.check_applicable(
                            invoice=self.move_id,
                            sit_iibb=perception_data['sit_iibb'],
                            from_padron=perception_data['from_padron'],
                            excluded_percent=perception_data['excluded_percent']
                        )
                        if applicable:
                            perceptions += perception
                tax_ids += perceptions
        if self.move_id.is_purchase_document(include_receipts=True) and self.move_id.perception_ids:
            tax_ids += self.move_id.perception_ids.mapped('perception_id')
        return tax_ids

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
