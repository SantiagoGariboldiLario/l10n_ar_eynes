import logging
from datetime import datetime

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = 'pos.order'

    invoice_journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Invoice Journal',
        copy=False,
    )
    is_wsfe = fields.Boolean(
        string='Is Electronic Invoice',
        copy=False,
    )

    def _export_for_ui(self, order):
        res = super(PosOrder, self)._export_for_ui(order)
        refunded_moves = order.refunded_order_ids.mapped('account_move')
        res['doc_origin'] = ', '.join(
            refunded_moves.mapped(lambda x: x.get_pretty_sequence())
        )
        return res

    @api.model
    def _order_fields(self, ui_order):
        res = super(PosOrder, self)._order_fields(ui_order)
        res['invoice_journal_id'] = ui_order['invoice_journal_id']
        res['is_wsfe'] = ui_order['inv_electronic_mode']
        return res

    def _prepare_invoice_vals(self):
        res = super(PosOrder, self)._prepare_invoice_vals()
        if self.invoice_journal_id:
            res['journal_id'] = self.invoice_journal_id.id
        fiscal_position = self.partner_id.property_account_position_id
        if fiscal_position:
            res['fiscal_position_id'] = fiscal_position.id
        if self.refunded_order_ids.account_move:
            res['associated_inv_ids'] = [
                (6, 0, self.refunded_order_ids.mapped('account_move').ids)
            ]
        return res

    def _hook_recompute_account_move(self, new_move):
        new_move._onchange_invoice_date()
        new_move.compute_perceptions()
        new_move._onchange_payment_term_date_invoice()
        return

    def _create_invoice(self, move_vals):
        res = super(PosOrder, self)._create_invoice(move_vals)
        self._hook_recompute_account_move(res)
        return res

    def _compute_all_vat_taxes(self, line_vals, order_vals):
        order_currency = self.env['res.currency'].browse(
            order_vals['currency_id']
        )
        product = self.env['product.product'].browse(line_vals['product_id'])
        partner = self.env['res.partner'].browse(order_vals['partner_id'])
        taxes = self.env['account.tax'].browse(line_vals['tax_ids'])
        account = self._get_computed_account(product, partner)

        currency = order_currency.with_context(
            date=order_vals['date'] or fields.Date.context_today(self)
        )
        company_currency = self.env.user.company_id.currency_id

        price_unit = line_vals['price']
        quantity = line_vals['qty']
        discount = line_vals['discount']
        price = price_unit * (1 - (discount or 0.0) / 100.0)
        price_subtotal = line_vals['price_subtotal']

        line_taxes = {}
        taxes = taxes.compute_all(
            price,
            order_currency,
            quantity,
            product,
            partner,
        )

        amount_tax = 0.0
        amount_base = 0.0
        amount_exempt = 0.0
        for tax in taxes['taxes']:
            if not tax['tax_group_name'].lower() == 'vat':
                continue

            val = {}
            val['name'] = tax['name']
            val['amount'] = tax['amount']
            val['base'] = tax['base']
            val['base_amount'] = currency.compute(
                val['base'], company_currency, round=False
            )
            val['tax_amount'] = currency.compute(
                val['amount'], company_currency, round=False
            )
            val['account_id'] = tax['account_id'] or account.id
            amount_tax += tax['amount']
            if tax['is_exempt']:
                amount_exempt += val['base']
            else:
                amount_base += val['base']

            line_taxes[tax['id']] = val

        return {
            'price_unit': price,
            'amount_untaxed': price_subtotal,
            'amount_total': amount_tax + price_subtotal,
            'amount_no_taxed': price_subtotal - amount_base - amount_exempt,
            'amount_exempt': amount_exempt,
            'amount_taxed': amount_base,
            'vat_taxes': line_taxes,
        }

    def _get_computed_account(self, product, partner):
        fiscal_position = partner.property_account_position_id
        accounts = product.product_tmpl_id.get_product_accounts(
            fiscal_pos=fiscal_position
        )
        return accounts['income']

    def _compute_base_perception(
        self, perception, perception_data, origin_vals=None
    ):
        if not origin_vals:
            return {}
        percent = perception_data['percent']

        concept_id = False

        partner = self.env['res.partner'].browse(origin_vals['partner_id'])

        # Por cada linea, nos fijamos la configuracion del producto
        perceptions = {}
        order_vals = origin_vals['order_vals']
        for line in order_vals['order_lines']:
            product = self.env['product.product'].browse(line['product_id'])
            account = self._get_computed_account(product, partner)
            taxapps = perception._get_taxapps(perception_data, account)
            if taxapps is None:
                continue

            concept_id = taxapps.concept_id.id

            # Obtenemos toda la info contable de la linea de factura
            # todas las cantidades y los impuestos de IVA aplicados
            res = self._compute_all_vat_taxes(line, order_vals)

            # Hacemos el computo de la Percepcion por linea de factura
            base = taxapps.compute_base(percent, res)

            if base == 0.0:
                continue

            # Luego vamos agrupando por Concepto (no por actividad)
            if concept_id in perceptions:
                perceptions[concept_id]['base'] += base
                # perceptions[concept_id]['amount'] += amount
                perceptions[concept_id]['lines'].append(line.id)
            else:
                perceptions[concept_id] = {
                    'base': base,
                    # 'amount': amount,
                    # 'lines': [line.id],
                    'reg_code': taxapps.reg_code,
                    'tax_app_id': taxapps,
                }
        return perceptions

    def _get_perceptions_ctx(self, order_vals):
        return {
            'partner_id': order_vals['partner_id'],
            'invoice_date': order_vals['date'],
            'amount_untaxed': order_vals['untaxed_amount'],
            'order_vals': order_vals,
        }

    @api.model
    def compute_perceptions(self, order_vals):
        journal_obj = self.env['account.journal']
        partner_id = order_vals['partner_id']
        if order_vals.get('date'):
            order_vals['date'] = datetime.strptime(
                order_vals['date'],
                '%Y-%m-%d',
            ).date()
        date = order_vals['date']
        if not partner_id:
            return 0.0
        partner = self.env['res.partner'].browse(partner_id)
        perception_ctx = self._get_perceptions_ctx(order_vals)
        perception_lst = journal_obj.get_applicable_perceptions(
            partner, self, origin_vals=perception_ctx, date=date
        )
        return sum(x['amount'] for x in perception_lst)
