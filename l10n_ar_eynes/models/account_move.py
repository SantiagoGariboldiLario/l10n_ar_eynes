import base64
import datetime
import json
import logging
import urllib.parse
from base64 import b64encode
from io import BytesIO

import qrcode

from odoo import SUPERUSER_ID, _, api, fields, models, registry
from odoo.exceptions import UserError, ValidationError
from odoo.tools import file_open

_logger = logging.getLogger(__name__)

# Constant used to find FCE type:
AFIP_FCE_CODE_START = 200


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
            ('ana', 'ANA'),
            ("not_defined", "Not Defined"),
        ],
        string='Denomination',
        compute='_compute_move_denomination',
        store=True,
    )
    disable_perceptions = fields.Boolean(default=False)
    iva_digital_operation_code = fields.Selection(
        [
            ('A', 'No Alcanzado'),
            ('NC', 'No corresponde'),
            ('C', 'Operac. Canje'),
            ('D', 'Devol. IVA Turistas Extr.'),
            ('E', 'Operaciones Exentas'),
            ('N', 'No gravado'),
            ('T', 'Reintegro Decreto 1043/2016'),
            ('X', 'Import. / Export. al Exterior'),
            ('Z', 'Import. / Export. a Zona Franca'),
        ],
        'Operation Code',
        default='NC',
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
    cae = fields.Char(
        string='CAE',
        size=32,
        required=False,
        copy=False,
        help='Codigo de Autorizacion Electronico assigned by AFIP.',
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
    voucher_type_domain = fields.Char(compute="_compute_voucher_type")
    ws_request_ids = fields.One2many(
        comodel_name='ws.request.detail', inverse_name='invoice_id'
    )
    local = fields.Boolean(related='fiscal_position_id.local')
    fiscal_type = fields.Selection(
        selection=[
            ('internal', 'Internal Invoice'),
            ('electronic', 'Electronic Invoice'),
        ],
        related='journal_id.fiscal_type',
        store=True,
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
    vat_date = fields.Date()

    _sql_constraints = [
        (
            'unique_move',
            'unique(partner_id, supplier_move_reference, is_debit_note)',
            _('This invoice was already entered.'),
        ),
    ]

    @api.depends('supplier_move_reference')
    def _compute_name(self):
        invoices = self.filtered(lambda move: move.is_invoice())
        for invoice in invoices:
            if invoice.state == 'draft':
                invoice.name = '/'
            elif invoice.is_sale_document():
                invoice.name = invoice.internal_number
            else:
                invoice.name = invoice.supplier_move_reference
        not_invoices = self - invoices
        return super(AccountMove, not_invoices)._compute_name()

    @api.depends('partner_id', 'journal_id')
    def _compute_move_denomination(self):
        for move in self:
            denomination = 'not_defined'
            if move.is_invoice():
                if move.is_sale_document() and move.journal_id:
                    denomination = move.journal_id.denomination
                elif move.is_purchase_document() and move.partner_id:
                    if not move.fiscal_position_id:
                        _logger.warning(
                            "You must configure a Fiscal Position for this Partner %s"
                            % move.partner_id.name
                        )
                    else:
                        denomination = (
                            move.fiscal_position_id.supplier_denomination
                        )
                        if not denomination:
                            _logger.warning(
                                "You must configure a Denomination for this Fiscal Position %s"
                                % move.fiscal_position_id.name
                            )
            move.denomination = denomination

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
        for invoice in self:
            res = {
                'amount_taxed_cur': 0.0,  # Gravado
                'amount_no_taxed_cur': 0.0,  # No gravado
                'amount_exempt_cur': 0.0,  # Exento
                'amount_untaxed_cur': 0.0,  # Subtotal sin impuestos
                'amount_tax_cur': 0.0,  # IVA
                'amount_perception_curr': 0.0,  # Percepciones
                'amount_total_cur': 0.0,  # Total
                'amount_fob_cur': 0.0,  # ??
            }

            secondary_currency = invoice.secondary_currency_id
            if (
                not secondary_currency
                or secondary_currency == invoice.currency_id
            ):
                invoice.update(res)
                continue

            for line in invoice.invoice_line_ids:
                amount = line.credit or line.debit
                res['amount_untaxed_cur'] += amount
                has_vat_tax = line.tax_ids.filtered(
                    lambda tax: tax.tax_group_id
                    and tax.tax_group_id.group_type == 'vat'
                )
                if has_vat_tax.filtered(lambda tax: tax.is_exempt):
                    res['amount_exempt_cur'] += amount
                elif has_vat_tax:
                    res['amount_taxed_cur'] += amount
                else:
                    res['amount_no_taxed_cur'] += amount
                res['amount_total_cur'] += amount

            for line in invoice.line_ids - invoice.invoice_line_ids:
                if not (
                    line.account_internal_type in ['payable', 'receivable']
                ):
                    amount = line.credit or line.debit
                    if (
                        line.tax_line_id.tax_group_id
                        and line.tax_line_id.tax_group_id.group_type == 'vat'
                    ):
                        res['amount_tax_cur'] += amount
                    if (
                        line.tax_line_id.tax_group_id
                        and line.tax_line_id.tax_group_id.group_type
                        == 'perception'
                    ):
                        res['amount_perception_curr'] += amount
                    res['amount_total_cur'] += amount

            invoice.update({field: val for field, val in res.items()})

    def get_highest_pos_sequence(
        self, journal, move_type, is_debit_note=False, is_fce=False
    ):
        """
        Returns the next number according to the
        type of invoice and journal
        """
        query = """
            SELECT max(sequence_number) AS next_sequence
            FROM account_move
            WHERE journal_id = %(journal_id)s
                AND fiscal_type = %(fiscal_type)s
                AND move_type = %(move_type)s
                AND is_debit_note = %(is_debit_note)s
                AND "is_FCE_invoice" = %(is_FCE_invoice)s
        """
        self.env.cr.execute(
            query,
            {
                'journal_id': journal.id,
                'fiscal_type': journal.fiscal_type,
                'move_type': move_type,
                'is_debit_note': is_debit_note,
                'is_FCE_invoice': is_fce,
            },
        )
        res = self.env.cr.fetchone()
        if not res:
            return '1'.zfill(8)
        return str(res[0] + 1).zfill(8)

    @api.onchange('partner_id')
    def _onchange_partner(self):
        if not self.partner_id:
            return
        super(AccountMove, self)._onchange_partner_id()
        if self.is_sale_document():
            partner_fiscal_position = (
                self.partner_id.property_account_position_id
            )
            journals = self.env.user.get_journals_by_fiscal_position(
                partner_fiscal_position
            )
            if not journals:
                self.journal_id = False
                self._onchange_journal()
                return {
                    'warning': {
                        'title': _('Journal not found'),
                        'message': _(
                            "Could not match any user available journals with fiscal position "
                            "'%(fiscal_pos)s'\n"
                            "Please check if there are any journals with this parameters "
                            "in users > preferences > available journals",
                            fiscal_pos=partner_fiscal_position.name,
                        ),
                    },
                    'domain': {'journal_id': [('id', 'in', [])]},
                }
            self.journal_id = journals[0]
            self._onchange_journal()
            self.suitable_journal_ids = journals

    @api.onchange('partner_id')
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
        """
        Update tax information based on perceptions.
        """
        if self.is_sale_document() or self.is_purchase_document():
            perceptions_applied = self.env['account.tax']
            for perception in self.perception_ids:
                perceptions_applied += perception.perception_id.tax_id

            for line in self.invoice_line_ids:
                line.tax_ids = (
                    line.tax_ids
                    - line.tax_ids.filtered(
                        lambda tax: tax.tax_group_id
                        and tax.tax_group_id.group_type == 'perception'
                    )
                ) | perceptions_applied

            if not self.env.context.get('is_reverse'):
                self.with_context(
                    override_perceptions=True
                )._recompute_tax_lines()

            self._recompute_dynamic_lines()

    @api.onchange('invoice_date')
    def _onchange_currency_id(self):
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

    @api.onchange('currency_rate')
    def _onchange_currency_rate(self):
        if self.is_invoice(include_receipts=True):
            for line in self._get_lines_onchange_currency():
                line.currency_rate = self.currency_rate
                line._onchange_currency()
            self.compute_perceptions()

    @api.onchange('date', 'currency_id')
    def _onchange_currency(self):
        super()._onchange_currency()
        self._onchange_currency_id()
        self._onchange_currency_rate()
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

    def _prepare_tax_line_vals(self, perception_line):
        """Prepare values to create an account.move.line

        The perception_line parameter is an perception.tax.line
        """
        perception_tax = perception_line.perception_id.tax_id
        sign = -1 if self.move_type in ('out_invoice', 'in_refund') else 1
        line_amount = amount_currency = perception_line.amount
        if self.is_multi_currency:
            line_amount = line_amount * self.currency_rate

        is_refund = self.move_type in ('out_refund', 'in_refund')
        account = perception_tax.get_perception_account(is_refund)
        return {
            'account_id': account.id,
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

        if not self.local:
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

    @api.depends(
        'denomination', 'move_type', 'is_debit_note', 'invoice_line_ids'
    )
    def _compute_voucher_type(self):
        ResVoucherType = self.env['res.voucher.type']
        for inv in self:
            inv_type = 'b'
            if inv.move_type.endswith("refund"):
                inv_type = 'cn'
            elif inv.is_debit_note:
                inv_type = 'dn'

            domain = [
                ('doc_type', '=', inv_type),
                ('denomination', '=', inv.denomination),
            ]

            inv.voucher_type_domain = json.dumps(domain)

            res = ResVoucherType.search(domain)
            if inv.is_sale_document():
                inv.is_FCE_invoice = False
                if inv._check_must_be_fce():
                    inv.is_FCE_invoice = True
                    res = res.filtered(
                        lambda voucher_type: int(voucher_type.afip_code)
                        > AFIP_FCE_CODE_START
                    )
                else:
                    res = res.filtered(
                        lambda voucher_type: int(voucher_type.afip_code)
                        < AFIP_FCE_CODE_START
                    )

                inv.voucher_type_id = res[0] if res else False
            if inv.is_purchase_document():
                if len(res) == 1:
                    inv.voucher_type_id = res

    @api.onchange('voucher_type_id')
    def _compute_is_FCE(self):
        if self.is_purchase_document():
            self.is_FCE_invoice = False
            if int(self.voucher_type_id.afip_code) > AFIP_FCE_CODE_START:
                self.is_FCE_invoice = True

    @api.onchange('invoice_date')
    def _onchange_invoice_date(self):
        super()._onchange_invoice_date()
        self.vat_date = self.invoice_date
        return

    @api.depends('invoice_line_ids')
    def _compute_amount_custom(self):
        def _filter_exempt(line):
            return any(line.tax_ids.mapped("is_exempt"))

        def _filter_untaxed(line):
            return not line.tax_ids

        def _filter_taxed(line):
            taxed = line.tax_ids.mapped(
                lambda x: x.tax_group_id
                and x.tax_group_id.group_type == 'vat'
                and not x.is_exempt
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

    def _set_perception_date(self):
        for inv in self:
            if (
                inv.is_sale_document() or inv.is_purchase_document()
            ) and inv.id:
                # If not date write the invoice date
                for p in inv.perception_ids:
                    if not p.date:
                        date = inv.invoice_date or fields.Date.context_today(
                            inv
                        )
                        p.write({'date': date})

    def _post(self, soft=True):
        for move in self:
            move.validate_period()
            if move.is_sale_document() and move.id:
                move.validate_denomination()

        posted_moves = super(AccountMove, self)._post(soft=soft)
        posted_moves._set_perception_date()

        return posted_moves

    def action_post(self):
        sale_invoices = self.filtered(lambda move: move.is_sale_document())
        electronic_invoices = sale_invoices.filtered(
            lambda move: move.fiscal_type == 'electronic'
        )
        for inv in sale_invoices - electronic_invoices:
            if not inv.posted_before:
                inv.write(
                    {
                        'internal_number': inv.journal_id.get_sequence_from_invoice(
                            inv
                        )._next()
                    }
                )

        super(AccountMove, self - electronic_invoices).action_post()

        return electronic_invoices._validate_electronic_invoices()

    def validate_period(self):
        date = self.date or self.invoice_date or fields.Date.context_today(self)
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

    @api.depends('restrict_mode_hash_table', 'state', 'cae')
    def _compute_show_reset_to_draft_button(self):
        sale_invoices = self.filtered(lambda move: move.is_sale_document())
        super(
            AccountMove, self - sale_invoices
        )._compute_show_reset_to_draft_button()
        for move in sale_invoices:
            move.show_reset_to_draft_button = False if move.cae else True
        return

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

    def action_register_payment(self):
        '''Open the account.payment.register wizard to pay the selected journal entries.
        :return: An action opening the account.payment.register wizard.
        '''
        try:
            self.ensure_one()
        except ValueError:
            return super(AccountMove, self).action_register_payment()

        view_id = self.env.ref(
            'l10n_ar_eynes.account_supplier_payment_order_view_form'
        )
        context = {
            'active_model': 'account.move',
            'default_disable_retentions': True,
        }
        if self.is_sale_document():
            view_id = self.env.ref(
                'l10n_ar_eynes.account_customer_payment_order_view_form'
            )
            context.update(
                {
                    'default_type': 'receipt',
                }
            )

        po = self.env['account.payment.order'].create(
            self._get_payment_order_vals()
        )

        return {
            'name': _('Register Payment'),
            'res_model': 'account.payment.order',
            'res_id': po.id,
            'view_mode': 'form',
            'view_id': view_id.id,
            'target': 'current',
            'context': context,
            'type': 'ir.actions.act_window',
        }

    def _get_payment_order_vals(self):
        move_line_domain = [
            ('id', 'in', self.line_ids.ids),
            ('reconciled', '=', False),
        ]
        if self.is_sale_document():
            move_line_domain += [
                ('debit', '>', 0),
                ('credit', '=', 0),
            ]
        else:
            move_line_domain += [
                ('debit', '=', 0),
                ('credit', '>', 0),
            ]
        move_lines = self.env['account.move.line'].search(move_line_domain)

        po_move_lines = []
        for move_line in move_lines:
            po_move_lines.append(
                (
                    0,
                    0,
                    {
                        'invoice_id': self.id,
                        'move_line_id': move_line.id,
                        'account_id': move_line.account_id.id,
                    },
                )
            )

        _type = 'receipt' if self.is_sale_document() else 'payment'
        po_vals = {
            'type': _type,
            'partner_id': self.partner_id.id,
            'journal_id': self._get_payment_order_journal(_type).id,
            'currency_id': self.currency_id.id,
        }

        if self.currency_id != self.company_id.currency_id:
            po_vals['payment_rate'] = self.currency_rate

        if self.is_sale_document():
            po_vals['income_line_ids'] = po_move_lines
        else:
            po_vals['debt_line_ids'] = po_move_lines

        return po_vals

    def _get_payment_order_journal(self, journal_type):
        domain = [('type', '=', journal_type)]
        if self.is_multi_currency:
            domain.append(
                ('currency_id', '=', self.currency_id.id),
            )
        journals = self.env['account.journal'].search(domain)
        if not journals:
            raise ValidationError(
                _("There are no payment/receipt journals with this currency.")
            )
        return journals[0]

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

        if perception_id.tax_id.apply_custom_code:
            new_perception_lines = self.env['perception.tax.line']

            perceptions = perception_id.tax_id._get_taxapps_from_code(
                perception_data, invoice=self
            )

            for perception_vals in perceptions:
                concept_id = perception_vals.get('concept_id')
                if not concept_id:
                    raise ValidationError(
                        _(
                            "Concept must be setted in python code. Perception %s"
                        )
                        % perception_id.name
                    )

                if (
                    perception_vals.get('amount', 0.0) == 0.0
                    and perception_id.tax_id.state_id.code != 'R'
                ):
                    continue

                # Creamos la percepcion.tax.line
                perception_line_vals = perception_id._prepare_perception_vals(
                    concept_id, perception_vals, self
                )
                # Creamos la perception.tax.line correspondiente
                # Le pasamos manual=False para que se cree la account.invoice.tax
                # con manual=False
                new_perception_lines += (
                    self.env['perception.tax.line']
                    .with_context(manual=False)
                    .new(perception_line_vals)
                )
            return new_perception_lines

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

    @api.onchange('invoice_line_ids', 'disable_perceptions', 'invoice_date')
    def compute_perceptions(self):
        for rec in self:
            if rec.is_sale_document():
                if rec.disable_perceptions:
                    rec.perception_ids.unlink()
                else:
                    new_perception_lines = self.env['perception.tax.line']
                    # Calculamos cada Percepcion configurada en el Partner
                    partner_perceptions = (
                        rec.partner_id._get_perceptions_to_apply(
                            rec.invoice_date or datetime.date.today()
                        )
                    )
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
            if rec.is_sale_document() or rec.is_purchase_document():
                rec._onchange_perception_ids()

    def _recompute_tax_lines(
        self,
        recompute_tax_base_amount=False,
        tax_rep_lines_to_recompute=None,
    ):
        modify_self = self.with_context(
            inverse_currency_rate=self.currency_rate
        )
        super(AccountMove, modify_self)._recompute_tax_lines(
            recompute_tax_base_amount,
            tax_rep_lines_to_recompute,
        )
        if self.is_purchase_document() or self.env.context.get(
            'override_perceptions', False
        ):
            for perception in self.perception_ids:
                move_line = self.line_ids.filtered(
                    lambda line: line.tax_line_id
                    == perception.perception_id.tax_id
                )
                vals = self._prepare_tax_line_vals(perception)
                move_line.update(vals)
        return

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

    def get_afip_logo_path(self):
        return "l10n_ar_eynes/static/img/logo_afip.png"

    def get_afip_logo(self):
        return b64encode(file_open(self.get_afip_logo_path(), 'rb').read())

    def price_subtotal_to_PDF(self):
        price_subtotal = self.amount_untaxed
        if self.denomination == 'b':
            price_subtotal += self.amount_tax
        return price_subtotal

    # --------------------------------------------------------------------------------
    # METHODS FOR ELECTRONIC INVOICES:
    def _get_ws_conf(self):
        WSFEConfig = self.env['wsfe.config']
        WSFEXConfig = self.env['wsfex.config']

        # We need to check that user isn't trying to send to AFIP different type of invoices
        local_list = self.mapped('local')
        if len(list(set(local_list))) != 1:
            raise UserError(
                _(
                    """
                    You are trying to send to AFIP Local Invoices and Export Invoices
                    """
                )
            )

        pos_ar_list = self.mapped('journal_id')
        if len(list(set(pos_ar_list))) != 1:
            raise UserError(
                _(
                    """
                    You are trying to send to AFIP Invoices from
                    different Point of Sales.
                    """
                )
            )

        ctx = self.env.context.copy()
        company = self.mapped('journal_id.company_id')
        if len(list(set(company))) != 1:
            raise UserError(
                _(
                    """
                    You are trying to send to AFIP Invoices from
                    different Companies.
                    """
                )
            )

        ctx['company_id'] = company.id

        wsfe_conf = WSFEConfig.with_context(**ctx).get_config()

        if local_list[0]:
            return wsfe_conf
        wsfex_conf = WSFEXConfig.with_context(**ctx).get_config()
        return wsfex_conf

    def _check_fce_using_abc(self):
        if not self.partner_id:
            return False
        if not self.partner_id.vat:
            return False
        ABC = self.env['afip.big.company'].sudo()
        is_bc = ABC.search([('cuit', '=like', self.partner_id.vat)])
        fcred_minimum_amount = self.company_id.fcred_minimum_amount
        return {
            'is_bc': is_bc,
            'fcred_minimum_amount': fcred_minimum_amount,
        }

    def _check_fce_using_ws(self):
        if not self.partner_id:
            return False
        if not self.partner_id.vat:
            return False
        ctx = self.env.context.copy()
        company = self.mapped('journal_id.company_id')
        if len(list(set(company))) != 1:
            raise UserError(
                _(
                    """
                    You are trying to check partner FCE situation for Invoices
                        from different Companies.
                    """
                )
            )

        ctx['company_id'] = company.id
        ws = self.env['wsfecred.config'].with_context(**ctx).get_config()
        amount = ws.check_partner_obliged_to_FCE(self)
        res = {
            'is_bc': True if amount else False,
            'fcred_minimum_amount': amount if amount else -1,
        }
        return res

    def _check_must_be_fce(self):
        """
        If the invoice matches some criteria, the invoice must be -FCE-
        """
        if (
            self.is_sale_document()
            and self.company_id.fcred_is_fce_emitter
            and self.fiscal_type == 'electronic'
        ):
            amount_total = (
                self.amount_total_cur
                if self.is_multi_currency
                else self.amount_total
            )
            res = None
            try:
                res = self._check_fce_using_ws()
            except Exception:
                _logger.warning('WSFECRED Fail.. trying old method..')
                res = self._check_fce_using_abc()

            if not res:
                return False

            if res['is_bc'] and amount_total > res['fcred_minimum_amount']:
                _logger.info(
                    'The Invoice ID: %s must be of type FCRED' % self.id
                )
                return True
        return False

    def _ensure_fce_values(self):
        """
        If invoice must be of type FCE, ensure certain values are set.
        """
        # Ensure Fiscal Type FCE
        self.is_FCE_invoice = True

        if self.associated_inv_ids:
            associated_type = self.associated_inv_ids.mapped('is_FCE_invoice')
            if False in associated_type:
                raise UserError(
                    _(
                        """
                        You can't associate non-FCE invoices to FCE invoice.
                        """
                    )
                )

        conf = self._get_ws_conf()
        set_optionals = True
        if self.is_debit_note or self.move_type == 'out_refund':
            set_optionals = False
            if not self.optional_ids.filtered(lambda opt: opt.code == '22'):
                raise UserError(
                    _(
                        """
                        You must inform optional with code '22' for this type of voucher.
                        Possible value: 'S' or 'N'
                        """
                    )
                )
        # Optionals
        if not self.optional_ids and set_optionals:
            WSOptionals = self.env['ws.optionals']
            aio_todo = WSOptionals.search(
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
                    if not value:
                        raise UserError(
                            _(
                                """
                                You need yo configure a CBU for FCE. Go to Settings --> Companies,
                                select %(name)s
                                and complete "CBU (FCE)" field.
                                """,
                                name=self.company_id.name,
                            )
                        )
                if aio.code == '27':
                    value = self.partner_id.fcred_transfer
                    if not value:
                        raise UserError(
                            _(
                                """
                                You need to configure the "SCA/ADC (FCE)?" field for this partner %(name)s.
                                """,
                                name=self.partner_id.name,
                            )
                        )
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
        if not pos_ar_id:
            raise UserError(
                _(
                    """
                    This invoice must be FCE but there aren't any
                    FCE Emitter Point of Sale configured.
                    """
                )
            )
        self.journal_id = pos_ar_id

    def _validate_electronic_invoices(self, soft=False):
        if self:
            posted_moves = self.env['account.move']
            with registry(self.env.cr.dbname).cursor() as new_cr:
                env = api.Environment(new_cr, SUPERUSER_ID, self.env.context)
                request = env['ws.request'].create(
                    {
                        'nregs': len(self),
                    }
                )
                new_cr.commit()  # pylint: disable=invalid-commit

                ws = self._get_ws_conf()

                for inv in self:
                    inv = env['account.move'].browse(inv.id)
                    if inv._check_must_be_fce():
                        inv._ensure_fce_values()
                    posted = inv._post(soft=soft)
                    if posted:
                        try:
                            ws.send_invoice_to_afip(inv, request)
                        except Exception:
                            new_cr.rollback()
                        else:
                            posted_moves += posted
                            new_cr.commit()  # pylint: disable=invalid-commit

                errors = self - posted_moves
                if errors:
                    context = dict(self._context or {})
                    context["message"] = _(
                        "Error trying to validate electronic invoice with ids [%(ids)s].\n"
                        "Check WS Requests page or go to 'Informs -> Ws Requests -> %(name)s'.",
                        ids=', '.join(str(inv_id.id) for inv_id in errors),
                        name=request.name,
                    )
                    view = self.env.ref("popup_messages.message_wizard")
                    view_id = view and view.id or False

                    return {
                        'name': _('WSFE Error'),
                        'type': 'ir.actions.act_window',
                        'view_mode': 'form',
                        'res_model': 'message.wizard',
                        'views': [(view_id, 'form')],
                        'view_id': view_id,
                        'target': 'new',
                        'context': context,
                    }
        return True

    def get_voucher_type(self):
        self.ensure_one()
        return int(self.voucher_type_id.afip_code)

    def get_pos(self):
        self.ensure_one()
        return int(self.journal_id.get_pos_number())

    def get_currency_code(self):
        self.ensure_one()
        WSCurrencyCodes = self.env['ws.currency.codes']
        currency_code_ids = WSCurrencyCodes.search(
            [('currency_id', '=', self.currency_id.id)]
        )

        if not currency_code_ids:
            raise UserError(
                _(
                    """
                    Currency %(curr_name)s has to be configured correctly
                    in WS Configuration.
                    """,
                    curr_name=self.currency_id.name,
                )
            )
        currency_code = currency_code_ids[0].code
        return currency_code

    def wsfe_relate_invoice(
        self, pos, number, voucher_type, date_invoice, cae, cae_due_date
    ):
        for inv in self:
            name = '%04d-%08d' % (pos, number)
            is_FCE = False
            if voucher_type in [
                self.env.ref('l10n_ar_eynes.factura_credito_electronica_a'),
                self.env.ref('l10n_ar_eynes.factura_credito_electronica_b'),
            ]:
                name = 'FCE' + name
                is_FCE = True
            elif voucher_type in [
                self.env.ref('l10n_ar_eynes.nota_credito_electronica_a'),
                self.env.ref('l10n_ar_eynes.nota_credito_electronica_b'),
            ]:
                name = 'NCCE' + name
                is_FCE = True
            elif voucher_type in [
                self.env.ref('l10n_ar_eynes.factura_debito_electronica_a'),
                self.env.ref('l10n_ar_eynes.factura_debito_electronica_b'),
            ]:
                name = 'NDCE' + name
                is_FCE = True

            invoice_vals = {
                'name': name,
                'internal_number': name,
                'invoice_date': date_invoice,
                'cae': cae,
                'cae_due_date': cae_due_date,
                'is_FCE_invoice': is_FCE,
            }

            # Escribimos los campos necesarios de la factura
            inv.write(invoice_vals)

            # Tomamos la factura y mandamos a realizar
            # el asiento contable.
            inv._post(soft=False)
            return
