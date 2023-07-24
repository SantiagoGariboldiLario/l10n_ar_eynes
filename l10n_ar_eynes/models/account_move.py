import base64
import datetime
import json
import logging
import urllib.parse
from io import BytesIO

import qrcode

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

# Constant used to find FCE type:
AFIP_FCE_CODE_START = 200
PCODES = {'nacional': '1', 'provincial': '2', 'municipal': '3'}


class AccountMove(models.Model):
    _inherit = 'account.move'

    denomination = fields.Selection(
        selection=[
            ("a", "A"),
            ("b", "B"),
            ("c", "C"),
            ("e", "E"),
            ('m', 'M'),
            ('oc', 'OC'),
            ("not_defined", "Not Defined"),
        ],
        string='Denomination',
    )
    internal_number = fields.Char(
        string='Internal Number',
        copy=False,
    )
    supplier_move_reference = fields.Char(
        string='Supplier Invoice Reference',
        copy=False,
    )
    address_shipping_id = fields.Many2one(
        comodel_name='res.partner',
        name='Shipping Address',
        readonly=True,
        required=False,
        states={'draft': [('readonly', False)]},
    )
    is_debit_note = fields.Boolean('Debit Note', default=False)
    perception_ids = fields.One2many(
        'perception.tax.line',
        'invoice_id',
        string='Perception',
        readonly=True,
        states={'draft': [('readonly', False)]},
    )
    aut_cae = fields.Boolean(
        'Autorizar',
        default=False,
        copy=False,
        help='Pedido de autorizacion a la AFIP',
    )
    cae = fields.Char(
        string='CAE/CAI',
        size=32,
        required=False,
        copy=False,
        help='CAE (Codigo de Autorizacion Electronico assigned by AFIP.)',
    )
    cae_due_date = fields.Date(
        'CAE Due Date',
        required=False,
        copy=False,
        help='Fecha de vencimiento del CAE',
    )
    associated_inv_ids = fields.Many2many(
        comodel_name='account.move',
        relation='inv_associated_inv_rel',
        column1='invoice_id',
        column2='associated_invoice_id',
        string='Assoiciated Invoices',
        readonly=True,
        states={'draft': [('readonly', False)]},
    )
    voucher_type_id = fields.Many2one(
        comodel_name='res.voucher.type',
        string='Voucher type',
        compute='_compute_voucher_type',
        store=True,
    )
    wsfe_request_ids = fields.One2many('wsfe.request.detail', 'name')
    local = fields.Boolean(related='fiscal_position_id.local')
    fiscal_type = fields.Selection(
        selection=[
            ('internal', 'Internal Invoice'),
            ('electronic', 'Electronic Invoice'),
        ],
        default='internal',
    )
    is_FCE_invoice = fields.Boolean(
        string="Is FCE?",
        default=False,
        help="Set True if this invoice must be treated as Electronic Invoice of Credit.",
    )
    amount_no_taxed = fields.Monetary(
        string='No Taxed',
        compute='_compute_amount_custom',
        store=True,
    )
    amount_taxed = fields.Monetary(
        string='Taxed',
        compute='_compute_amount_custom',
        store=True,
    )
    amount_exempt = fields.Monetary(
        string='Except',
        compute='_compute_amount_custom',
        store=True,
    )
    # Campos para facturas de exportacion. Aca ninguno es requerido,
    # eso lo hacemos en la vista ya que depende de
    # si es o no factura de exportacion
    export_type_id = fields.Many2one('wsfex.export.type.codes', 'Export Type')
    dst_country_id = fields.Many2one('wsfex.dst.country.codes', 'Dest Country')
    shipping_perm_ids = fields.One2many(
        'wsfex.shipping.permission',
        'invoice_id',
        'Shipping Permissions',
    )
    wsfex_request_ids = fields.One2many('wsfex.request.detail', 'invoice_id')
    optional_ids = fields.One2many(
        'account.move.optional',
        'invoice_id',
        'Optionals',
    )
    dst_cuit_id = fields.Many2one('dst.cuit.codes', 'Country CUIT')
    currency_preciated = fields.Boolean(
        related='currency_id.preciated',
        string="Currency Preciated",
        readonly=True,
    )
    currency_rate = fields.Float(
        string='Currency Rate',
        digits=(12, 6),
        readonly=True,
        states={'draft': [('readonly', False)]},
        default=lambda x: 1.00,
        help="It is the preciated currency rate of the invoice",
    )
    is_multi_currency = fields.Boolean(
        string='Multi Currency Invoice',
        default=False,
        help="""Fields with internal purpose only that depicts
                if the invoice is a multi currency one or not""",
    )
    currency_converted = fields.Boolean(
        'Invoice Converted',
        default=False,
        help="""If this invoice was fill as multicurrency and then
                converted to local currency, this will be checked""",
    )
    secondary_currency_id = fields.Many2one(
        'res.currency',
        string='Secondary Currency',
        readonly=True,
        states={'draft': [('readonly', False)]},
        default=lambda x: x.env.user.company_id.currency_id,
    )
    secondary_currency_rate = fields.Float(
        string='Secondary Currency Rate',
        digits=(12, 6),
        readonly=True,
        states={'draft': [('readonly', False)]},
        default=lambda x: 1.00,
        help="It is the old currency rate of the last change of currency",
    )
    company_currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda x: x.env.user.company_id.currency_id,
    )
    amount_exempt_cur = fields.Monetary(
        compute='_compute_amount_all_cur',
        store=True,
        readonly=True,
        currency_field="secondary_currency_id",
        string='Amount Exempt',
    )
    amount_no_taxed_cur = fields.Monetary(
        compute='_compute_amount_all_cur',
        store=True,
        readonly=True,
        currency_field="secondary_currency_id",
        string='No Taxed',
    )
    amount_taxed_cur = fields.Monetary(
        compute='_compute_amount_all_cur',
        store=True,
        readonly=True,
        currency_field="secondary_currency_id",
        string='Taxed',
    )
    amount_untaxed_cur = fields.Monetary(
        compute='_compute_amount_all_cur',
        store=True,
        readonly=True,
        currency_field="secondary_currency_id",
        string='Untaxed',
    )
    amount_tax_cur = fields.Monetary(
        compute='_compute_amount_all_cur',
        store=True,
        readonly=True,
        currency_field="secondary_currency_id",
        string='Tax',
    )
    amount_perception_curr = fields.Monetary(
        compute='_compute_amount_all_cur',
        store=True,
        readonly=True,
        currency_field="secondary_currency_id",
        string='Perceptions',
    )
    amount_total_cur = fields.Monetary(
        compute='_compute_amount_all_cur',
        store=True,
        readonly=True,
        currency_field="secondary_currency_id",
        string='Total',
    )
    amount_fob_cur = fields.Monetary(
        compute='_compute_amount_all_cur',
        store=True,
        readonly=True,
        currency_field="secondary_currency_id",
        string='FOB',
    )
    is_company_cur = fields.Boolean(compute='_compute_is_company_cur')
    vat_date = fields.Date()

    @api.depends('supplier_move_reference')
    def _compute_name(self):
        invoices = self.filtered(lambda move: move.is_invoice())
        for invoice in invoices:
            if invoice.is_sale_document():
                if invoice.state == 'draft':
                    invoice.name = '/'
                else:
                    invoice.name = invoice.internal_number
            else:
                invoice.name = invoice.supplier_move_reference
        not_invoices = self - invoices
        return super(AccountMove, not_invoices)._compute_name()

    @api.depends(
        'invoice_line_ids',
        'invoice_line_ids.price_unit',
        'invoice_line_ids.tax_ids',
        'invoice_line_ids.quantity',
        'invoice_line_ids.discount',
        'currency_rate',
        'perception_ids',
    )
    def _compute_amount_all_cur(self):
        Currency = self.env.get('res.currency')
        for invoice in self:
            res = {
                'amount_untaxed_cur': 0.0,
                'amount_tax_cur': 0.0,
                'amount_perception_curr': 0.0,
                'amount_total_cur': 0.0,
                'amount_fob_cur': 0.0,
                'amount_taxed_cur': 0.0,
                'amount_no_taxed_cur': 0.0,
                'amount_exempt_cur': 0.0,
            }

            secondary_currency = invoice.secondary_currency_id
            if (
                not secondary_currency
                or secondary_currency == invoice.currency_id
            ):
                invoice.update(res)
                continue

            amount_base = 0.0
            amount_exempt = 0.0

            for line in invoice.invoice_line_ids:
                res['amount_untaxed_cur'] += line.price_subtotal

                for tax in line.tax_ids:
                    if tax.tax_group_id == self.env.ref(
                        'l10n_ar_eynes.perceptions_tax_group',
                        raise_if_not_found=False,
                    ):
                        continue
                    if tax.tax_group_id == self.env.ref(
                        'l10n_ar_eynes.vat_tax_group',
                        raise_if_not_found=False,
                    ):
                        if tax.is_exempt:
                            amount_exempt += tax.amount
                        else:
                            amount_base += tax.amount
                    res['amount_tax_cur'] += invoice.currency_id.round(
                        line.price_subtotal * tax.amount * 0.01
                    )

            date = invoice.date or invoice.date_invoice or fields.Date.today()
            company = invoice.company_id
            modify_cur_obj = Currency.with_context(
                currency1=(invoice.currency_id, invoice.currency_rate),
                currency2=(secondary_currency, invoice.secondary_currency_rate),
            )
            rate = modify_cur_obj._get_conversion_rate(
                invoice.currency_id,
                secondary_currency,
                company,
                date,
            )

            res['amount_total_cur'] *= rate
            res['amount_untaxed_cur'] *= rate
            res['amount_tax_cur'] *= rate
            res['amount_perception_curr'] = invoice.currency_id.round(
                sum(invoice.perception_ids.mapped('amount'))
                * invoice.currency_rate
            )
            amount_base *= rate
            amount_exempt *= rate

            atc_rounded = secondary_currency.round(res['amount_tax_cur'])
            atotc_rounded = secondary_currency.round(res['amount_total_cur'])
            auc_rounded = secondary_currency.round(res['amount_untaxed_cur'])
            perc_rounded = secondary_currency.round(
                res['amount_perception_curr']
            )
            amount_base = secondary_currency.round(amount_base)
            amount_exempt = secondary_currency.round(amount_exempt)

            res['amount_total_cur'] = atc_rounded + auc_rounded + perc_rounded
            res['amount_fob_cur'] = atotc_rounded
            res['amount_no_taxed_cur'] = (
                auc_rounded - amount_base - amount_exempt
            )
            res['amount_taxed_cur'] = amount_base
            res['amount_exempt_cur'] = amount_exempt
            invoice.update({field: val for field, val in res.items()})

    def compute_invoice_totals(self, company_currency, invoice_move_lines):
        modify_self = self.with_context(
            currency1=(self.currency_id, self.currency_rate),
            currency2=(company_currency, 1),
        )
        return super(AccountMove, modify_self).compute_invoice_totals(
            company_currency, invoice_move_lines
        )

    def _compute_is_company_cur(self):
        for invoice in self:
            invoice.is_company_cur = (
                invoice.company_currency_id == invoice.currency_id
            )

    def get_highest_pos_sequence(self):
        invoices = self.env['account.move'].search(
            [
                ('journal_id', '=', self.journal_id.id),
                ('move_type', '=', self.move_type),
                ('is_debit_note', '=', self.is_debit_note),
                ('is_FCE_invoice', '=', self.is_FCE_invoice),
            ]
        )

        if not invoices or len(invoices) == 1:
            return '1'.zfill(8)

        last_sequence_number = max(invoices.mapped('sequence_number'))
        return str(last_sequence_number + 1).zfill(8)

    # ONCHANGE METHODS
    @api.onchange('journal_id', 'partner_id')
    def _onchange_journal(self):
        if not self.partner_id:
            return
        if self.journal_id.type == 'sale':
            super(AccountMove, self)._onchange_journal()
            self.denomination = self.journal_id.denomination

    @api.onchange('partner_id', 'fiscal_type')
    def _onchange_partner(self):
        if not self.partner_id:
            return
        super(AccountMove, self)._onchange_partner_id()
        if self.is_sale_document():
            partner_fiscal_position = (
                self.partner_id.property_account_position_id
            )
            journals = self.env.user.journal_ids.filtered(
                lambda j: partner_fiscal_position in j.fiscal_position_ids
            )
            if self.fiscal_type:
                journals = journals.filtered(
                    lambda journal: journal.fiscal_type == self.fiscal_type
                )
            if journals:
                self.journal_id = journals[0]
                self._onchange_journal()
                return {'domain': {'journal_id': [('id', 'in', journals.ids)]}}

    @api.onchange('partner_id', 'company_id')
    def _onchange_partner_id(self):
        res = super(AccountMove, self)._onchange_partner_id()
        if self.is_sale_document():
            # If partner changes set the partner_id for existent perceptions
            perception_ids = self.perception_ids.ids
            if self.partner_id and perception_ids:
                upd_lst = [
                    (1, p, {'partner_id': self.partner_id})
                    for p in perception_ids
                ]
                self.perception_ids = upd_lst
        return res

    @api.onchange('perception_ids')
    def _onchange_perception_ids(self):
        if self.is_sale_document() or self.is_purchase_document():
            perceptions_applied = self.env['account.tax']
            for perception in self.perception_ids:
                perceptions_applied += perception.perception_id.tax_id

            for line in self.invoice_line_ids:
                line.tax_ids += perceptions_applied

            if not self.env.context.get('is_reverse'):
                self._recompute_tax_lines()

                for perception in self.perception_ids:
                    move_line = self.line_ids.filtered(
                        lambda line: line.tax_line_id
                        == perception.perception_id.tax_id
                    )
                    vals = self._prepare_tax_line_vals(perception)
                    move_line.update(vals)

            self._recompute_dynamic_lines()

    @api.onchange('currency_id', 'invoice_date')
    def _onchange_currency_id(self):
        self._compute_is_company_cur()
        date_invoice = self.date or self.invoice_date or fields.Date.today()
        if not self.currency_id:
            self.is_multi_currency = False
            # self.currency_rate = 1.0
        else:
            company = self.env.user.company_id
            company_currency = company.currency_id
            currency = self.currency_id
            if currency != company_currency:
                curr_rate = currency._get_currency_rate(company, date_invoice)
                self.is_multi_currency = True
                if currency.preciated:
                    self.currency_rate = curr_rate.inverse_company_rate
                else:
                    self.currency_rate = curr_rate.company_rate
            else:
                self.is_multi_currency = False
                self.currency_rate = 1.0

        self._onchange_payment_term_date_invoice()
        return

    @api.onchange('invoice_payment_term_id', 'invoice_date')
    def _onchange_payment_term_date_invoice(self):
        date_invoice = self.invoice_date
        if not date_invoice:
            date_invoice = fields.Date.context_today(self)
        if self.invoice_payment_term_id:
            pterm = self.invoice_payment_term_id
            pterm_list = pterm.with_context(
                currency_id=self.company_id.currency_id.id
            ).compute(value=1, date_ref=date_invoice)[0]
            self.invoice_date_due = pterm_list[0]
        elif self.invoice_date_due and (date_invoice > self.invoice_date_due):
            self.invoice_date_due = date_invoice

    def _get_refund_common_fields(self):
        res = super(AccountMove, self)._get_refund_common_fields()
        res.append('currency_rate')
        return res

    def get_invoice_amounts_in_company_cur(self):
        res = {}
        for inv in self:
            if inv.is_multi_currency and not inv.currency_converted:
                res[inv.id] = {
                    'amount_total': inv.amount_total_cur,
                    'amount_exempt': inv.amount_exempt_cur,
                    'amount_no_taxed': inv.amount_no_taxed_cur,
                    'amount_taxed': inv.amount_taxed_cur,
                    'amount_untaxed': inv.amount_untaxed_cur,
                    'amount_tax': inv.amount_tax_cur,
                    'amount_fob': inv.amount_fob_cur,
                }
            else:
                res[inv.id] = {
                    'amount_total': inv.amount_total,
                    'amount_exempt': inv.amount_exempt,
                    'amount_no_taxed': inv.amount_no_taxed,
                    'amount_taxed': inv.amount_taxed,
                    'amount_untaxed': inv.amount_untaxed,
                    'amount_tax': inv.amount_tax,
                    # 'amount_fob': inv.amount_fob
                }

        return res

    def _prepare_tax_line_vals(self, perception_line):
        """Prepare values to create an account.move.line

        The perception_line parameter is an perception.tax.line
        """
        perception_tax = perception_line.perception_id.tax_id
        sign = -1 if self.move_type in ('out_invoice', 'in_refund') else 1
        line_amount = amount_currency = perception_line.amount
        if not self.is_company_cur:
            line_amount = line_amount * self.currency_rate

        return {
            'account_id': perception_tax.tax_group_id.property_tax_payable_account_id.id,
            'price_unit': line_amount,
            'credit': line_amount
            if self.move_type in ('out_invoice', 'in_refund')
            else 0,
            'debit': line_amount
            if self.move_type not in ('out_invoice', 'in_refund')
            else 0,
            'balance': sign * line_amount,
            'amount_currency': sign * amount_currency,
            'price_subtotal': line_amount,
            'price_total': line_amount,
            'tax_base_amount': perception_line.base,
            'sequence': perception_tax.tax_group_id.sequence,
        }

    @api.onchange(
        'supplier_move_reference',
        'denomination',
        'fiscal_position_id',
        'partner_id',
    )
    def _onchange_supplier_move_reference(self):
        if not self.supplier_move_reference:
            return

        # Separator missing or multiple separators error
        if self.supplier_move_reference.count('-') != 1:
            raise ValidationError(_('Must be only one separator'))

        pos_code, move_code = self.supplier_move_reference.split('-')
        if not pos_code or not move_code:
            raise ValidationError(
                _('numbers missing after or before separator')
            )
        if not pos_code.isnumeric() or not move_code.isnumeric():
            raise ValidationError(_('the reference must be numbers only'))
        if len(pos_code) > 5 or len(move_code) > 8:
            raise ValidationError(_('Some of the fields exceeds length'))

        self.supplier_move_reference = (
            pos_code.zfill(4) + '-' + move_code.zfill(8)
        )

    @api.onchange('fiscal_position_id', 'partner_id')
    def _onchange_fiscal_position(self):
        fiscal_position = (
            self.fiscal_position_id
            or self.partner_id.property_account_position_id
        )
        if self.is_purchase_document():
            self.denomination = fiscal_position.supplier_denomination

    @api.depends('denomination', 'move_type', 'is_debit_note', 'is_FCE_invoice')
    def _compute_voucher_type(self):
        for inv in self:
            if inv.is_sale_document():
                voucher_type_obj = inv.env['res.voucher.type']
                res = self.env['res.voucher.type']

                inv_type = 'b'
                if inv.move_type.endswith("refund"):
                    inv_type = 'cn'
                elif inv.is_debit_note:
                    inv_type = 'dn'

                res = voucher_type_obj.search(
                    [
                        ('doc_type', '=', inv_type),
                        ('denomination', '=', inv.denomination),
                    ]
                )

                if not len(res):
                    _logger.warning(
                        _(
                            "There is no voucher type that corresponds "
                            "to this object"
                        )
                    )

                if inv.is_FCE_invoice:
                    res = res.filtered(
                        lambda voucher_type: int(voucher_type.afip_code)
                        > AFIP_FCE_CODE_START
                    )
                else:
                    res = res.filtered(
                        lambda voucher_type: int(voucher_type.afip_code)
                        < AFIP_FCE_CODE_START
                    )

                if len(res) > 1:
                    _logger.warning(
                        _(
                            "There is more than one voucher type that "
                            "corresponds to this object"
                        )
                    )
                else:
                    inv.voucher_type_id = res

    @api.onchange('date', 'currency_id', 'currency_rate')
    def _onchange_currency(self):
        super()._onchange_currency()
        if self.is_invoice(include_receipts=True):
            for line in self._get_lines_onchange_currency():
                line.currency_rate = self.currency_rate
                line._onchange_product_id()
                line._onchange_currency()
            self.compute_perceptions()
        return

    @api.onchange('invoice_date')
    def _onchange_invoice_date(self):
        self.vat_date = self.invoice_date

    @api.depends('invoice_line_ids')
    def _compute_amount_custom(self):
        def _filter_exempt(line):
            return any(line.tax_ids.mapped("is_exempt"))

        def _filter_untaxed(line):
            return not line.tax_ids

        def _filter_taxed(line):
            taxed = line.tax_ids.mapped(
                lambda x: x.tax_group_id.name == 'vat' and not x.is_exempt
            )
            return any(taxed)

        for inv in self:
            # Amount exempt
            inv.amount_exempt = sum(
                inv.invoice_line_ids.filtered(_filter_exempt).mapped(
                    "price_subtotal"
                )
            )

            # Amount untaxed
            inv.amount_no_taxed = sum(
                inv.invoice_line_ids.filtered(_filter_untaxed).mapped(
                    "price_subtotal"
                )
            )

            # Amount taxed
            inv.amount_taxed = sum(
                inv.invoice_line_ids.filtered(_filter_taxed).mapped(
                    "price_subtotal"
                )
            )

    def get_voucher_type(self):
        self.ensure_one()
        return int(self.voucher_type_id.afip_code)

    def get_pos(self):
        self.ensure_one()
        return int(self.journal_id.get_pos_number())

    def get_next_wsfe_number(self, conf=False):
        self.ensure_one()
        if not conf:
            conf = self.get_ws_conf()
        _logger.info(self)
        inv = self
        tipo_cbte = self.get_voucher_type()
        try:
            pto_vta = inv.get_pos()
        except ValueError as value_err:
            err = _(
                'Error\nEl nombre del punto de venta tiene que ser numerico'
            )
            raise UserError(err) from value_err

        last = conf.get_last_voucher(pto_vta, tipo_cbte)

        return int(last + 1)

    def get_last_date_invoice(self):
        self.ensure_one()

        last_invoice = self.env['account.move'].search(
            [
                ('journal_id', '=', self.journal_id.id),
                ('state', 'in', ['open', 'paid', 'cancel']),
                ('move_type', '=', self.move_type),
                ('is_debit_note', '=', self.is_debit_note),
                ('is_FCE_invoice', '=', self.is_FCE_invoice),
            ],
            order="invoice_date desc",
            limit=1,
        )

        return last_invoice.invoice_date if last_invoice else False

    def check_must_be_fce(self):
        """
        If the invoice matches some criteria, the invoice must be of credit -FCE-
        """
        if not self.company_id.fcred_is_fce_emitter:
            return False
        if self.move_type not in ('out_invoice', 'out_refund'):
            return False
        ABC = self.env['afip.big.company'].sudo()
        is_bc = ABC.search([('cuit', '=like', self.partner_id.vat)])
        amount_total = (
            self.amount_total_cur
            if self.is_multi_currency
            else self.amount_total
        )
        fcred_minimum_amount = self.company_id.fcred_minimum_amount
        if is_bc and amount_total > fcred_minimum_amount:
            _logger.info('The %s must be of type FCRED' % self)
            return True
        return False

    def ensure_fce_values(self):
        """
        If invoice must be of type FCE, ensure certain values are set.
        """
        # Ensure Fiscal Type FCE
        self.is_FCE_invoice = True
        conf = self.get_ws_conf()
        set_optionals = True
        if self.is_debit_note or self.move_type == 'out_refund':
            set_optionals = False
        # Optionals
        if not self.optional_ids and set_optionals:
            WO = self.env['wsfe.optionals']
            aio_todo = WO.search(
                [
                    ('code', 'in', ('2101', '27')),
                    ('wsfe_config_id', '=', conf.id),
                ]
            )
            # 2101: cbu del emisor, 27 sca|adc
            aios = []
            for aio in aio_todo:
                if aio.code == '2101':
                    value = self.company_id.fcred_cbu_emitter
                if aio.code == '27':
                    value = self.partner_id.fcred_transfer
                dd = {
                    'optional_id': aio.id,
                    'value': value,
                }
                aios.append((0, 0, dd))
            self.optional_ids = aios
        # Point Of Sale
        pos_ar_id = (
            self.env['account.journal'].search(
                [
                    ('fcred_is_fce_emitter', '=', True),
                    ('warehouse_id', '=', self.journal_id.warehouse_id.id),
                ]
            )
            or self.company_id.fcred_pos_ar_id.id
        )
        if pos_ar_id:
            self.journal_id = pos_ar_id

    def _set_perception_date(self):
        # If not date write the invoice date
        for p in self.perception_ids:
            if not p.date:
                date = self.invoice_date or fields.Date.context_today(self)
                p.write({'date': date})

    def action_post(self):
        if self.is_sale_document():
            if self.id:
                self.validate_denomination()
                self.validate_period()
                if self.fiscal_type == 'electronic':
                    if self.check_must_be_fce():
                        self.ensure_fce_values()
                    self.action_aut_cae()
                else:
                    if not self.posted_before:
                        self.write(
                            {
                                'internal_number': self.journal_id.get_sequence_from_invoice(
                                    self
                                )._next()
                            }
                        )
                self._set_perception_date()
        return super(AccountMove, self).action_post()

    def validate_period(self):
        date = self.invoice_date or fields.Date.context_today(self)
        if not self.journal_id.due_date:
            raise ValidationError(
                _(
                    "The journal does not have a period established\n"
                    "Please add a period in: "
                    "accounting/journals/update journals periods"
                )
            )
        if date < self.journal_id.due_date:
            raise ValidationError(
                _(
                    "You are trying to create an invoice with a date older date "
                    "than the allowed by the journal"
                )
            )

    def validate_denomination(self):
        if not self.denomination or self.denomination == 'not_defined':
            raise ValidationError(
                _("Invoice must have a denomination configured")
            )

    def action_post_from_massive(self, first_number):
        for rec in self:
            rec.validate_denomination()
            rec.validate_period()
            if rec.check_must_be_fce():
                rec.ensure_fce_values()

        logs = self._validate_electronic_invoices(first_number)
        super(AccountMove, self).action_post()
        return logs

    def button_draft(self):
        for rec in self:
            if rec.aut_cae:
                err = _(
                    "You cannot send to draft this Electronic Invoice "
                    "because it has been informed to AFIP."
                )
                raise ValidationError(err)
        return super(AccountMove, self).button_draft()

    @api.model
    def hook_add_taxes(self, inv, detalle):
        perc_array = []

        for perception in inv.perception_ids:
            code = PCODES[perception.perception_id.tax_id.jurisdiccion]
            perc = {
                'Id': code,
                'BaseImp': round(perception.base / inv.currency_rate, 2)
                if not inv.is_company_cur
                else perception.base,
                'Importe': round(perception.amount / inv.currency_rate, 2)
                if not inv.is_company_cur
                else perception.amount,
                'Alic': 0.0,
                'Desc': perception.name,
            }
            perc_array.append(perc)

        if detalle.get('Tributos'):
            detalle['Tributos']['Tributo'] += perc_array
        else:
            detalle['Tributos'] = {'Tributo': perc_array}

        return detalle

    def action_aut_cae(self):
        self.ensure_one()
        self._validate_electronic_invoices()
        return True

    def _validate_electronic_invoices(self, first_number=False):
        # if not all(self.mapped('aut_cae')):
        #     return True

        # self._sanitize_taxes()
        ws = self.new_ws()
        new_cr = self.pool.cursor()
        uid = self.env.user.id
        ctx = self.env.context
        inv_model = self.env['account.move']
        try:
            invoices_approved = ws.send_invoices(
                self, first_number=first_number
            )

            for invoice_id, invoice_vals in invoices_approved.items():
                invoice = inv_model.browse(invoice_id)
                invoice.write({**invoice_vals})
            # Commit the info given by AFIP that was written to the invoice
            # to prevent desynchronizations
            # self.env.cr.commit()
        except Exception as e:
            # Simply reraise if the exception is already controlled
            _logger.exception('WSFE Validation Error')
            if isinstance(e, UserError):
                raise
            err = _(
                'WSFE Validation Error\n' 'Error received was: \n %s'
            ) % repr(e)
            raise UserError(err) from e
        finally:
            # Creamos el wsfe.request con otro cursor,
            # porque puede pasar que
            # tengamos una excepcion e igualmente,
            # tenemos que escribir la request
            # Sino al hacer el rollback se pierde hasta el wsfe.request
            # self.env.cr.rollback()
            try:
                with api.Environment.manage():
                    new_env = api.Environment(new_cr, uid, ctx)
                    logs = ws.log_request(new_env)
                    new_cr.commit()
                    new_cr.close()
            except Exception:
                _logger.exception('Unable to log afip request')
                logs = None
            else:
                _logger.info('Success in logging afip request')
        return logs

    def wsfe_relate_invoice(self, pos, number, date_invoice, cae, cae_due_date):
        for inv in self:
            name = '%04d-%08d' % (pos, number)
            invoice_vals = {
                'name': name,
                'payment_reference': name,
                'invoice_date': date_invoice,
                'cae': cae,
                'cae_due_date': cae_due_date,
                'state': 'open',
            }

            # Escribimos los campos necesarios de la factura
            inv.write(invoice_vals)

            # Tomamos la factura y mandamos a realizar
            # el asiento contable.
            inv._post(soft=False)
            return

    def new_ws(self, conf=False):
        if not conf:
            conf = self.get_ws_conf()
        ws = conf._webservice_class(conf.url)
        return ws

    def ws_auth(self, ws=False, conf=False):
        # TODO WSAA To easywsy and this could float between WSAA & WSFE
        if not conf:
            conf = self.get_ws_conf()
        token, sign = conf.wsaa_ticket_id.get_token_sign()
        auth = {'Token': token, 'Sign': sign, 'Cuit': conf.cuit}
        if not ws:
            ws = conf._webservice_class(conf.url)
        ws.login('Auth', auth)
        return ws

    def complete_date_invoice(self):
        for inv in self:
            if not inv.invoice_date:
                inv.write(
                    {
                        'invoice_date': fields.Date.context_today(self),
                    }
                )

    def check_invoice_total(self, calculated_total):
        # Chequeamos que el Total calculado por Odoo, se corresponda
        # con el total calculado por nosotros, tal vez puede haber un error
        # de redondeo
        obj_precision = self.env['decimal.precision']
        prec = obj_precision.precision_get('Account')
        if round(calculated_total, prec) != round(self.amount_total, prec):
            raise UserError(
                _(
                    "Error in amount_total!\n"
                    "The total amount of the invoice does not "
                    "match the total calculated.\n"
                    "Maybe there is a rounding error!. "
                    "(Amount Calculated: %f)"
                )
                % (calculated_total)
            )

    def get_ws_conf(self):
        wsfe_conf_obj = self.env['wsfe.config']
        wsfex_conf_obj = self.env['wsfex.config']
        local_list = self.mapped('local')
        if len(list(set(local_list))) != 1:
            err = _(
                "Trying to get the WSFE config for invoices mixed "
                "between local and not local"
            )
            raise UserError(_("WSFE Error\n") + err)
        ctx = self.env.context.copy()
        company = self.mapped('journal_id.company_id')
        company.ensure_one()
        # ^- Raise if trying to validate invoice of != companies
        ctx['company_id'] = company.id

        ctx.setdefault('without_raise', True)
        wsfe_conf = wsfe_conf_obj.with_context(**ctx).get_config()
        wsfex_conf = wsfex_conf_obj.with_context(**ctx).get_config()

        pos_ar_list = self.mapped('journal_id')
        if len(list(set(pos_ar_list))) != 1:
            err = _(
                "Trying to get the WSFE config for invoices that "
                "belong to different points of sale"
            )
            raise UserError(_("WSFE Error\n") + err)
        pos_ar = pos_ar_list[0]
        # Chequeamos si corresponde Factura Electronica
        # Aca nos fijamos si el pos_ar_id tiene
        # factura electronica asignada
        confs_list = []
        for c in [wsfe_conf, wsfex_conf]:
            conf = c.point_of_sale_ids
            if pos_ar in conf:
                confs_list.append(c)

        if len(confs_list) > 1:
            err = (
                _("There is more than one configuration " "with this POS %s")
                % pos_ar.name
            )
            raise UserError(_("WSFE Error\n") + err)

        if confs_list:
            confs_obj = confs_list[0]
        elif not ctx['without_raise']:
            err = (
                _("There is no configuration for this " "POS %s") % pos_ar.name
            )
            raise UserError(_("WSFE Error\n") + err)
        else:
            confs_obj = False
        return confs_obj

    def get_currency_code(self):
        # Obtenemos la moneda de la factura
        # Lo hacemos por el wsfex_config, por cualquiera de ellos
        # si es que hay mas de uno
        self.ensure_one()
        currency_code_obj = self.env['wsfex.currency.codes']
        currency_code_ids = currency_code_obj.search(
            [('currency_id', '=', self.currency_id.id)]
        )

        if not currency_code_ids:
            raise UserError(
                _(
                    "WSFE Error!\n"
                    "Currency has to be configured correctly "
                    "in WSFEX Configuration."
                )
            )
        currency_code = currency_code_ids[0].code
        return currency_code

    @api.model_create_multi
    def create(self, vals):
        res = super().create(vals)
        for move in res:
            if not move.invoice_date:
                move.write({'invoice_date': datetime.date.today()})
            if move.is_invoice():
                if not move.denomination:
                    if move.is_sale_document():
                        denomination = move.journal_id.denomination
                    else:
                        denomination = (
                            move.partner_id.property_account_position_id.supplier_denomination
                        )
                    move.write({'denomination': denomination})
        return res

    # def action_register_payment(self):
    #     """Override to redirect to account payment order"""
    #     po = self.env['account.payment.order'].create(
    #         self.get_payment_order_vals()
    #     )

    #     if self.is_sale_document():
    #         view_id = self.env.ref(
    #             'l10n_ar_eynes.account_customer_payment_order_view_form'
    #         )
    #     else:
    #         view_id = self.env.ref(
    #             'l10n_ar_eynes.account_supplier_payment_order_view_form'
    #         )
    #     return {
    #         'name': _('Customer Payment'),
    #         'res_model': 'account.payment.order',
    #         'res_id': po.id,
    #         'view_mode': 'form',
    #         'view_id': view_id.id,
    #         'target': 'current',
    #         'type': 'ir.actions.act_window',
    #     }

    # def get_payment_order_vals(self):
    #     move_line_domain = [
    #         ('id', 'in', self.line_ids.ids),
    #         ('reconciled', '=', False),
    #     ]
    #     if self.is_sale_document():
    #         move_line_domain += [
    #             ('debit', '>', 0),
    #             ('credit', '=', 0),
    #         ]
    #     else:
    #         move_line_domain += [
    #             ('debit', '=', 0),
    #             ('credit', '>', 0),
    #         ]
    #     move_line = self.env['account.move.line'].search(move_line_domain)
    #     po_move_line = [
    #         (
    #             0,
    #             0,
    #             {
    #                 'invoice_id': self.id,
    #                 'move_line_id': move_line.id,
    #                 'account_id': move_line.account_id.id,
    #             },
    #         )
    #     ]

    #     _type = 'receipt' if self.is_sale_document() else 'payment'
    #     po_vals = {
    #         'type': _type,
    #         'partner_id': self.partner_id.id,
    #         'journal_id': self.get_payment_order_journal(_type).id,
    #     }

    #     if self.currency_id != self.company_id.currency_id:
    #         po_vals['payment_rate'] = self.currency_rate

    #     if self.is_sale_document():
    #         po_vals['income_line_ids'] = po_move_line
    #     else:
    #         po_vals['debt_line_ids'] = po_move_line

    #     return po_vals

    # def get_payment_order_journal(self, journal_type):
    #     journals = self.env['account.journal'].search(
    #         [
    #             ('type', '=', journal_type),
    #             ('currency_id', '=', self.currency_id.id),
    #         ]
    #     )
    #     if not journals:
    #         raise ValidationError(
    #             _("There are no payment/receipt journals with this currency.")
    #         )
    #     return journals[0]

    @api.constrains('name', 'journal_id', 'state')
    def _check_unique_sequence_number(self):
        moves = self.filtered(lambda move: move.state == 'posted')
        if not moves:
            return

        self.flush(['name', 'journal_id', 'move_type', 'state'])

        # /!\ Computed stored fields are not yet inside the database.
        self._cr.execute(
            '''
            SELECT move2.id, move2.name
            FROM account_move move
            INNER JOIN account_move move2 ON
                move2.name = move.name
                AND move2.journal_id = move.journal_id
                AND move2.move_type = move.move_type
                AND move2.is_debit_note = move.is_debit_note
                AND move2.id != move.id
                AND move2.partner_id = move.partner_id
            WHERE move.id IN %s AND move2.state = 'posted'
        ''',
            [tuple(moves.ids)],
        )
        res = self._cr.fetchall()
        if res:
            raise ValidationError(
                _(
                    'Posted journal entry must have an unique sequence number per company.\n'
                    'Problematic numbers: %s\n'
                )
                % ', '.join(r[1] for r in res)
            )

    @api.model
    def compute_perception(self, perception_data):
        perception_id = perception_data['perception']
        # Chequeamos si la Percepcion tiene seteado un state_id, que coincida
        # con el state_id de la direccion de entrega del partner.
        # Sino no se realiza la Percepcion
        partner_model = self.env['res.partner']
        destination_shipping = self.address_shipping_id or partner_model.browse(
            self.partner_id.address_get(['delivery']).get('delivery')
        )
        source_shipping = self.env.user.company_id.partner_id
        applicable = perception_id.check_applicable(
            sit_iibb=perception_data['sit_iibb'],
            from_padron=perception_data['from_padron'],
            source_shipping_id=source_shipping,
            destination_shipping_id=destination_shipping,
        )
        if not applicable:
            return None

        # Chequeamos las percepciones a aplicar que matchean
        # (esto corresponde a una percepcion pero que pueden
        # existir varios conceptos y/o actividades)
        perceptions = perception_id._compute_base_perception(
            perception_data, self
        )

        # Creamos las lineas de percepcion
        new_perception_lines = self.env['perception.tax.line']
        for concept_id, vals in perceptions.items():
            # Aplicamos la percepcion por Concepto
            taxapp = vals['tax_app_id']

            base, amount = taxapp.apply_perception(vals, perception_data)

            if amount == 0.0:
                continue

            vals['amount'] = amount
            vals['base'] = base

            # Creamos la percepcion.tax.line
            perception_line_vals = perception_id._prepare_perception_vals(
                concept_id, vals, self
            )
            new_perception_lines += (
                self.env['perception.tax.line']
                .with_context(manual=False)
                .new(perception_line_vals)
            )
        return new_perception_lines

    def _reverse_move_vals(self, default_values, cancel=True):
        vals = super(AccountMove, self)._reverse_move_vals(
            default_values, cancel=cancel
        )

        perceptions = []
        for p in self.perception_ids:
            perceptions.append(
                (
                    0,
                    0,
                    {
                        'amount': p.amount,
                        'base': p.base,
                        'base_amount': p.base_amount,
                        'concept_id': p.concept_id.id,
                        'manual': p.manual,
                        'name': p.name,
                        'partner_id': p.partner_id.id,
                        'perception_id': p.perception_id.id,
                        'reg_code': p.reg_code,
                        'state_id': p.state_id.id,
                        'tax_amount': p.tax_amount,
                        'tax_app_id': p.tax_app_id.id,
                        'vat': p.vat,
                    },
                )
            )
        vals.update(
            {
                # 'address_shipping_id': self.address_shipping_id.id,
                'perception_ids': perceptions,
            }
        )

        return vals

    @api.onchange('invoice_line_ids')
    def compute_perceptions(self):
        for rec in self:
            if rec.is_sale_document():
                new_perception_lines = self.env['perception.tax.line']
                # Calculamos cada Percepcion configurada en el Partner
                partner_perceptions = rec.partner_id._get_perceptions_to_apply()
                for partner_perc in partner_perceptions.values():
                    excluded_percent = partner_perc['excluded_percent']

                    # Chequeamos las fechas de eximision
                    vdate = rec.invoice_date or datetime.date.today()

                    first_day_of_year = datetime.date.min.replace(
                        year=datetime.date.today().year
                    )
                    last_day_of_year = datetime.date.max.replace(
                        year=datetime.date.today().year
                    )
                    date_from = first_day_of_year
                    date_to = last_day_of_year
                    if partner_perc['ex_date_from']:
                        date_from = partner_perc['ex_date_from']
                    if partner_perc['ex_date_to']:
                        date_to = partner_perc['ex_date_to']

                    # TODO: Chequear cuando solo se llena uno de las dos fechas
                    if (not date_from and not date_to) or (
                        vdate >= date_from and vdate <= date_to
                    ):
                        if excluded_percent > 1.0 or excluded_percent < 0.0:
                            raise ValidationError(
                                _(
                                    "Perception Configuration Error!\n"
                                    + "Excluded percent configured has to be "
                                    + "between 0.0 and 1.0"
                                )
                            )

                        # Si esta totalmente eximido
                        if excluded_percent == 1.0:
                            continue
                    else:
                        partner_perc['excluded_percent'] = 0.0
                    new_perception = rec.compute_perception(
                        perception_data=partner_perc
                    )
                    if new_perception:
                        new_perception_lines += new_perception
                rec.perception_ids = new_perception_lines
                rec._onchange_perception_ids()

    def _recompute_tax_lines(
        self,
        recompute_tax_base_amount=False,
        tax_rep_lines_to_recompute=None,
    ):
        modify_self = self.with_context(
            inverse_currency_rate=self.currency_rate
        )
        return super(AccountMove, modify_self)._recompute_tax_lines(
            recompute_tax_base_amount,
            tax_rep_lines_to_recompute,
        )

    def _generate_qr_afip_url(self):
        voucher_type = self.get_voucher_type()
        pos = self.get_pos()
        date_dt = self.invoice_date.strftime("%Y-%m-%d")
        invoice_qr_data = {
            'ver': 1,
            'fecha': date_dt,
            'cuit': int(self.partner_id.vat or '0'),
            'ptoVta': pos,
            'tipoCmp': voucher_type,
            'nroCmp': int(self.name.split('-')[1]),
            'importe': round(self.amount_total, 2),
            'moneda': str(self.currency_id.name or ''),
            'ctz': "%.6f" % (self.amount_total),
            'tipoDocRec': int(
                self.partner_id.document_type_id.afip_code or '0'
            ),
            'nroDocRec': int(self.partner_id.vat or '0'),
            'tipoCodAut': 'E',
            'codAut': int(self.cae or '0') or '00000000000000',
        }
        data = json.dumps(invoice_qr_data)
        qr_text = 'https://www.afip.gob.ar/fe/qr/?p=' + base64.b64encode(
            bytes(data, 'utf-8')
        ).decode('utf-8')
        qr_text = urllib.parse.quote(qr_text)

        return qr_text

    def _generate_qr(self, txt=''):
        qr_code = qrcode.QRCode(version=4, box_size=4, border=1)
        qr_code.add_data(txt)
        qr_code.make(fit=True)
        qr_img = qr_code.make_image()
        im = qr_img._img.convert("RGB")
        buffered = BytesIO()
        im.save(buffered, format="JPEG")
        img_str = base64.b64encode(buffered.getvalue()).decode('ascii')

        return img_str

    def get_qr_code(self):
        if not self.cae:
            return False
        url = self._generate_qr_afip_url()
        return self._generate_qr(url)

    def _get_name_invoice_report(self):
        """This method need to be inherit by the localizations if they want to
        print a custom invoice report instead of
        the default one. For example please review the l10n_ar module"""
        self.ensure_one()
        return 'l10n_ar_eynes.report_invoice_document'

    _sql_constraints = [
        (
            'unique_move',
            'unique(partner_id, supplier_move_reference, is_debit_note)',
            _('This invoice reference already exists for this supplier'),
        ),
    ]


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
    currency_rate = fields.Float(
        'Currency Rate',
        digits=(12, 6),
        readonly=False,
        help="It is the currency rate",
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
