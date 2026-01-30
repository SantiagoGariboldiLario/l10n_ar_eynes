import base64
import json
import logging
import urllib.parse
from base64 import b64encode
from io import BytesIO

import qrcode

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import file_open
from odoo.tools.safe_eval import safe_eval
from odoo.tools.sql import (
    column_exists,
    create_column,
    drop_index,
    index_exists,
)

_logger = logging.getLogger(__name__)

# Constant used to find FCE type:
AFIP_FCE_CODE_START = 200


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _auto_init(self):
        """
        Se modifica la validación de base ya que no permite que se carguen dos facturas con la misma
        numeración y esto para Proveedores es algo posible, por lo tanto debemos permitirlo. Creamos la
        validación para poder crear facturas de proveedores que posean la misma numeración siempre y cuando
        sean de proveedores distintos.
        """
        if not column_exists(self.env.cr, "account_move", "is_debit_note"):
            create_column(
                self.env.cr, "account_move", "is_debit_note", "boolean"
            )
        if not (
            index_exists(self.env.cr, "account_move_unique_name_customers")
            or index_exists(self.env.cr, "account_move_unique_name_suppliers")
        ):
            drop_index(self.env.cr, "account_move_unique_name", self._table)
            self.env.cr.execute(
                """
                CREATE UNIQUE INDEX account_move_unique_name
                    ON account_move(name, journal_id)
                    WHERE (state = 'posted' AND name != '/' AND move_type = 'entry');
                CREATE UNIQUE INDEX account_move_unique_name_customers
                    ON account_move(name, journal_id, move_type, is_debit_note)
                    WHERE (
                        state = 'posted' AND name != '/'
                        AND move_type IN ('out_invoice', 'out_refund', 'out_receipt')
                    );
                CREATE UNIQUE INDEX account_move_unique_name_suppliers
                    ON account_move(name, partner_id, journal_id, move_type, is_debit_note)
                    WHERE (
                        state = 'posted' AND name != '/'
                        AND move_type IN ('in_invoice', 'in_refund', 'in_receipt')
                    );
                """
            )
        return super()._auto_init()

    # ==================================================================================
    # ============================================================================
    # COMMENTED OUT - Using _prepare_tax_lines override instead (cleaner approach)
    # Uncomment this block if _prepare_tax_lines approach doesn't work
    # ============================================================================
    #
    # # v19 Migration: _sync_tax_lines override to redistribute perception/internal taxes
    # # This replaces the v17 _compute_all_tax logic that no longer exists in v19
    # # ==================================================================================
    # @contextmanager
    # def _sync_tax_lines(self, container):
    # """
    # Override to redistribute perception and internal tax amounts across product lines.
    # Replicates the v17 _compute_all_tax logic.
    #
    # CAMBIO v19: En v17, _compute_all_tax modificaba el campo binario compute_all_tax.
    # En v19, ese campo no existe, así que modificamos directamente las líneas de impuestos
    # después de que el método padre las cree.
    # """
    # # Call the parent implementation first
    # with super()._sync_tax_lines(container) as result:
    # yield result
    #
    # # After yield: tax lines have been created/updated by the parent
    # # Now apply the Argentinian perception/internal tax redistribution
    # for move in container['records']:
    # if move.state != 'draft':
    # continue
    # self._redistribute_argentinian_taxes(move)
    #
    # def _redistribute_argentinian_taxes(self, move):
    # """
    # Redistribute perception and internal tax amounts proportionally across product lines.
    # This replicates the logic from v17's _compute_all_tax in account.move.line.
    #
    # LÓGICA ORIGINAL: El método original en v17 tomaba los totales de perception_ids e
    # internal_taxes_ids y los redistribuía proporcionalmente entre las líneas de producto.
    # Ahora hacemos lo mismo pero escribiendo directamente a las tax lines.
    # """
    # if not move.is_invoice(include_receipts=True):
    # return
    #
    # sign = -1 if move.is_inbound() else 1
    # product_lines = move.line_ids.filtered(lambda l: l.display_type == 'product')
    # tax_lines = move.line_ids.filtered(lambda l: l.display_type == 'tax')
    #
    # # ==================== PERCEPTIONS ====================
    # # CAMBIO v19: En v17 se modificaba compute_all_tax[key]['balance'].
    # # En v19, escribimos directamente a la línea de impuesto correspondiente.
    # if hasattr(move, 'perception_ids') and move.perception_ids:
    # perception_taxes = product_lines.tax_ids.filtered(
    # lambda tax: tax.tax_group_id and tax.tax_group_id.group_type == 'perception'
    # )
    # for perception in perception_taxes:
    # perception = perception._origin
    # # Find the tax line for this perception
    # # NOTA: En v19, tax_line_id es el impuesto que generó esta línea
    # perception_tax_line = tax_lines.filtered(
    # lambda tl: tl.tax_line_id == perception
    # )
    # if not perception_tax_line:
    # continue
    #
    # # Get total from perception_ids (the user-entered values)
    # # LÓGICA ORIGINAL: Igual que en v17, sumamos base y amount de perception_ids
    # perception_total_base = sum(
    # move.perception_ids.filtered(
    # lambda ptl: ptl.perception_id == perception
    # ).mapped('base')
    # )
    # perception_total_amount = sum(
    # move.perception_ids.filtered(
    # lambda ptl: ptl.perception_id == perception
    # ).mapped('amount')
    # )
    #
    # # Update the tax line with the correct amounts
    # # CAMBIO v19: Write directo en lugar de modificar diccionario
    # rate = perception_tax_line.currency_rate or 1.0
    # perception_tax_line.write({
    # 'amount_currency': sign * perception_total_amount,
    # 'balance': sign * perception_total_amount / rate,
    # })
    #
    # # ==================== INTERNAL TAXES ====================
    # # LÓGICA ORIGINAL: Solo para documentos de compra con internal_taxes_ids
    # if move.is_purchase_document() and hasattr(move, 'internal_taxes_ids') and move.internal_taxes_ids:
    # internal_taxes = product_lines.tax_ids.filtered(
    # lambda tax: tax.tax_group_id and tax.tax_group_id.group_type == 'internals'
    # )
    # for internal_tax in internal_taxes:
    # internal_tax = internal_tax._origin
    # # Find the tax line for this internal tax
    # internal_tax_line = tax_lines.filtered(
    # lambda tl: tl.tax_line_id == internal_tax
    # )
    # if not internal_tax_line:
    # continue
    #
    # # Get total from internal_taxes_ids
    # internal_total_base = sum(
    # move.internal_taxes_ids.filtered(
    # lambda ptl: ptl.tax_id == internal_tax
    # ).mapped('base')
    # )
    # internal_total_amount = sum(
    # move.internal_taxes_ids.filtered(
    # lambda ptl: ptl.tax_id == internal_tax
    # ).mapped('amount')
    # )
    #
    # # Update the tax line
    # # CAMBIO v19: Write directo
    # rate = internal_tax_line.currency_rate or 1.0
    # internal_tax_line.write({
    # 'amount_currency': sign * internal_total_amount,
    # 'balance': sign * internal_total_amount / rate,
    # })
    #
    #
    # *******************************************************************************************************
    #                                       MISCELANEOUS FIELDS:
    # *******************************************************************************************************
    amount_exempt = fields.Monetary(
        string='Except',
        compute='_compute_amount_custom',
        store=True,
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
    created_from_rej_check = fields.Boolean(default=False)
    internal_number = fields.Char(
        string='Internal Number',
        copy=False,
    )
    is_closing = fields.Boolean(default=False)
    is_opening = fields.Boolean(default=False)
    local = fields.Boolean(related='fiscal_position_id.local')
    show_fiscal_credit = fields.Boolean(
        default=lambda self: self.env["ir.config_parameter"]
        .sudo()
        .get_param("l10n_ar_eynes.apportionable_vat"),
        store=False,
    )
    supplier_move_reference = fields.Char(
        string='Supplier Invoice Reference',
        copy=False,
    )
    # *******************************************************************************************************
    #                        Facturación según estándares fiscales de Argentina:
    # *******************************************************************************************************
    associated_inv_ids = fields.Many2many(
        comodel_name='account.move',
        relation='inv_associated_inv_rel',
        column1='invoice_id',
        column2='associated_invoice_id',
        string='Assoiciated Invoices',
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
    fiscal_type = fields.Selection(
        related='journal_id.fiscal_type',
        store=True,
    )
    inform_cbu = fields.Boolean(default=False)
    inform_period = fields.Boolean(default=False)
    inform_period_date_from = fields.Date()
    inform_period_date_to = fields.Date()
    is_debit_note = fields.Boolean('Debit Note', default=False)
    voucher_type_domain = fields.Char(compute="_compute_voucher_type_domain")
    voucher_type_id = fields.Many2one(
        comodel_name='res.voucher.type',
        string='Voucher type',
        store=True,
        readonly=False,
    )
    # FACTURA DE CRÉDITO ELECTRONICA:
    is_FCE_invoice = fields.Boolean(
        string="Is FCE?",
        default=False,
        help="Set True if this invoice must be treated as Electronic Invoice of Credit.",
    )
    optional_ids = fields.One2many(
        'account.move.optional',
        'invoice_id',
        'Optionals',
    )
    # FACTURA DE EXPORTACIÓN:
    dst_country_id = fields.Many2one('wsfex.dst.country.codes', 'Dest Country')
    dst_cuit_id = fields.Many2one('dst.cuit.codes', 'Country CUIT')
    export_type_id = fields.Many2one('wsfex.export.type.codes', 'Export Type')
    shipping_perm_ids = fields.One2many(
        'wsfex.shipping.permission',
        'invoice_id',
        'Shipping Permissions',
    )
    # REPORTE LIBRO IVA DIGITAL:
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
    # RESULTADO WEBSERVICES:
    ws_request_ids = fields.One2many(
        comodel_name='ws.request.detail', inverse_name='invoice_id'
    )
    # *******************************************************************************************************
    #                                             Percepciones:
    # *******************************************************************************************************
    disable_perceptions = fields.Boolean(default=False)
    perception_ids = fields.One2many(
        'perception.tax.line',
        'invoice_id',
        string='Perception',
        copy=True,
    )
    # *******************************************************************************************************
    #                                             Multimoneda:
    # *******************************************************************************************************
    currency_preciated = fields.Boolean(
        related='currency_id.preciated',
        string="Currency Preciated",
        readonly=True,
    )
    currency_rate = fields.Float(
        string='Currency Rate',
        digits=(12, 6),
        default=lambda x: 1.00,
        help="It is the preciated currency rate of the invoice",
    )
    is_multi_currency = fields.Boolean(
        string='Multi Currency Invoice',
        default=False,
        help="""Fields with internal purpose only that depicts
                if the invoice is a multi currency one or not""",
    )
    same_currency_cancel = fields.Boolean(default=False)
    show_get_arca_currency_btn = fields.Boolean(
        compute='_compute_show_get_arca_currency_btn'
    )
    show_same_currency_cancel = fields.Boolean(
        compute='_compute_show_same_currency_cancel'
    )
    secondary_currency_id = fields.Many2one(
        'res.currency',
        string='Secondary Currency',
        readonly=True,
        default=lambda x: x.env.company.currency_id,
    )
    secondary_currency_rate = fields.Float(
        string='Secondary Currency Rate',
        digits=(12, 6),
        readonly=True,
        default=lambda x: 1.00,
        help="It is the old currency rate of the last change of currency",
    )
    # MONTOS EN MONEDA (currency_id):
    amount_exempt_cur = fields.Monetary(
        compute='_compute_amount_all_cur',
        store=True,
        readonly=True,
        currency_field="company_currency_id",
        string='Amount Exempt',
    )
    amount_no_taxed_cur = fields.Monetary(
        compute='_compute_amount_all_cur',
        store=True,
        readonly=True,
        currency_field="company_currency_id",
        string='No Taxed',
    )
    amount_taxed_cur = fields.Monetary(
        compute='_compute_amount_all_cur',
        store=True,
        readonly=True,
        currency_field="company_currency_id",
        string='Taxed',
    )
    amount_subtotal_cur = fields.Monetary(
        compute='_compute_amount_all_cur',
        store=True,
        readonly=True,
        currency_field="company_currency_id",
        string='Untaxed',
    )
    amount_tax_cur = fields.Monetary(
        compute='_compute_amount_all_cur',
        store=True,
        readonly=True,
        currency_field="company_currency_id",
        string='Tax',
    )
    amount_perception_curr = fields.Monetary(
        compute='_compute_amount_all_cur',
        store=True,
        readonly=True,
        currency_field="company_currency_id",
        string='Perceptions',
    )
    amount_total_cur = fields.Monetary(
        compute='_compute_amount_all_cur',
        store=True,
        readonly=True,
        currency_field="company_currency_id",
        string='Total',
    )
    # *******************************************************************************************************
    #                                        Impuestos Internos:
    # *******************************************************************************************************
    internal_taxes_ids = fields.One2many(
        'internal.tax.line',
        'invoice_id',
        string='Internal',
        copy=True,
    )

    _sql_constraints = [
        (
            'unique_move',
            'unique(partner_id, supplier_move_reference, is_debit_note, move_type)',
            _('This invoice was already entered.'),
        ),
        (
            'unique_name_customers',
            '',
            _('Another entry with the same name already exists.'),
        ),
        (
            'unique_name_suppliers',
            '',
            _('Another entry with the same name already exists.'),
        ),
    ]

    @api.constrains('invoice_date_due', 'invoice_date')
    def _check_invoice_date_due_after_invoice(self):
        for record in self:
            if (
                record.invoice_date
                and record.invoice_date_due
                and record.invoice_date_due < record.invoice_date
            ):
                raise ValidationError(
                    _(
                        'The due date must be equal to or later than the invoice date.'
                    )
                )

    @api.constrains('denomination')
    def _check_denomination_not_m(self):
        for record in self:
            if record.denomination == 'm':
                raise ValidationError(
                    _("M denomination is not allowed since December 1° 2025.")
                )

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
        'currency_rate',
        'tax_totals',
        'amount_taxed',
        'amount_no_taxed',
        'amount_exempt',
    )
    def _compute_amount_all_cur(self):
        for invoice in self.filtered(
            lambda move: move.is_invoice(include_receipts=True)
        ):
            res = {
                'amount_taxed_cur': 0.0,  # Gravado
                'amount_no_taxed_cur': 0.0,  # No gravado
                'amount_exempt_cur': 0.0,  # Exento
                'amount_subtotal_cur': 0.0,  # Subtotal sin impuestos
                'amount_perception_curr': 0.0,  # Percepciones
                'amount_tax_cur': 0.0,  # IVA
                'amount_total_cur': 0.0,  # Total
            }

            if invoice.is_multi_currency:
                if invoice.company_currency_id != invoice.currency_id:
                    rate = invoice.currency_rate
                else:
                    rate = 1 / invoice.secondary_currency_rate

                res['amount_taxed_cur'] = invoice.amount_taxed * rate
                res['amount_no_taxed_cur'] = invoice.amount_no_taxed * rate
                res['amount_exempt_cur'] = invoice.amount_exempt * rate

                res['amount_total_cur'] += res['amount_taxed_cur']
                res['amount_total_cur'] += res['amount_no_taxed_cur']
                res['amount_total_cur'] += res['amount_exempt_cur']

                if invoice.tax_totals and invoice.tax_totals.get('subtotals'):
                    for subtotal in invoice.tax_totals['subtotals']:
                        for tax in subtotal.get('tax_groups', []):
                            group = self.env['account.tax.group'].browse(
                                tax['id']
                            )
                            base_amount_currency = tax.get(
                                'base_amount_currency', 0.0
                            )
                            tax_amount_currency = tax.get(
                                'tax_amount_currency', 0.0
                            )
                            if group.group_type == 'vat':
                                res['amount_subtotal_cur'] = (
                                    base_amount_currency * invoice.currency_rate
                                )
                                res['amount_tax_cur'] = (
                                    tax_amount_currency * rate
                                )
                                res['amount_total_cur'] += res['amount_tax_cur']
                            elif group.group_type == 'perception':
                                res['amount_perception_curr'] = (
                                    tax_amount_currency * rate
                                )
                                res['amount_total_cur'] += res[
                                    'amount_perception_curr'
                                ]

            invoice.update(res)

    @api.depends('move_type', 'currency_id', 'company_currency_id')
    def _compute_show_same_currency_cancel(self):
        for move in self:
            show = False
            if (
                move.move_type in ('out_invoice', 'out_refund')
                and move.currency_id != move.company_currency_id
            ):
                show = True
            move.show_same_currency_cancel = show

    @api.depends(
        'move_type',
        'currency_id',
        'company_currency_id',
        'state',
        'same_currency_cancel',
    )
    def _compute_show_get_arca_currency_btn(self):
        for move in self:
            show = False
            if (
                move.move_type in ('out_invoice', 'out_refund')
                and move.state == 'draft'
                and move.currency_id != move.company_currency_id
                and move.same_currency_cancel
            ):
                show = True
            move.show_get_arca_currency_btn = show

    def get_highest_pos_sequence(
        self, journal, move_type, is_debit_note=False, is_fce=False
    ):
        """
        Returns the next number according to the
        type of invoice and journal
        """
        query = """
            SELECT COALESCE(MAX(sequence_number), 0) AS next_sequence
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
        super()._onchange_partner_id()
        if self.is_sale_document():
            partner_fiscal_position = (
                self.partner_id.property_account_position_id
            )
            if not partner_fiscal_position:
                raise UserError(
                    _('You must set a Fiscal Position for %s')
                    % self.partner_id.name
                )
            journals = self.env.user.get_journals_by_fiscal_position(
                partner_fiscal_position
            )
            if not journals:
                self.journal_id = False
                self._inverse_journal_id()
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
            self._inverse_journal_id()
            self.suitable_journal_ids = journals
            self.invoice_line_ids.force_compute_tax_ids()

    @api.depends_context('lang')
    @api.depends(
        'invoice_line_ids.currency_rate',
        'invoice_line_ids.tax_base_amount',
        'invoice_line_ids.tax_line_id',
        'invoice_line_ids.price_total',
        'invoice_line_ids.price_subtotal',
        'invoice_payment_term_id',
        'partner_id',
        'currency_id',
        'perception_ids',
        'internal_taxes_ids',
    )
    def _compute_tax_totals(self):
        """Computed field used for custom widget's rendering.
        Only set on invoices.
        """
        # pylint: disable=missing-return
        super()._compute_tax_totals()
        for move in self:
            if move.is_invoice(include_receipts=True):
                totals = move.tax_totals
                if not totals:
                    continue
                currency = move.currency_id
                company_currency = move.company_currency_id

                for subtotal in totals.get('subtotals', []):
                    for tax_group in subtotal.get('tax_groups', []):
                        group = self.env['account.tax.group'].browse(
                            tax_group['id']
                        )
                        if group.group_type not in ('perception', 'internals'):
                            continue
                        if (
                            group.group_type == 'internals'
                            and not move.is_purchase_document()
                        ):
                            continue

                        old_tax_amount_currency = tax_group.get(
                            'tax_amount_currency', 0.0
                        )
                        old_tax_amount = tax_group.get('tax_amount', 0.0)
                        # old_base_amount_currency = tax_group.get(
                        #     'base_amount_currency', 0.0
                        # )
                        # old_base_amount = tax_group.get('base_amount', 0.0)

                        if group.group_type == 'perception':
                            base_currency = sum(
                                move.perception_ids.mapped('base')
                            )
                            amount_currency = sum(
                                move.perception_ids.mapped('amount')
                            )
                        else:
                            base_currency = sum(
                                move.internal_taxes_ids.mapped('base')
                            )
                            amount_currency = sum(
                                move.internal_taxes_ids.mapped('amount')
                            )

                        base_amount = currency._convert(
                            base_currency,
                            company_currency,
                            move.company_id,
                            move.date or fields.Date.context_today(move),
                        )
                        tax_amount = currency._convert(
                            amount_currency,
                            company_currency,
                            move.company_id,
                            move.date or fields.Date.context_today(move),
                        )

                        tax_group.update(
                            {
                                'base_amount_currency': base_currency,
                                'tax_amount_currency': amount_currency,
                                'base_amount': base_amount,
                                'tax_amount': tax_amount,
                            }
                        )

                        delta_tax_currency = (
                            amount_currency - old_tax_amount_currency
                        )
                        delta_tax = tax_amount - old_tax_amount
                        # delta_base_currency = (
                        #     base_currency - old_base_amount_currency
                        # )
                        # base_amount - old_base_amount

                        # FIX v19: Solo sumar deltas de tax_amount, NO de base_amount
                        # El base_amount ya está correctamente calculado por el core.
                        # Sumar delta_base causaba doble conteo del subtotal.
                        subtotal['tax_amount_currency'] += delta_tax_currency
                        subtotal['tax_amount'] += delta_tax
                        # subtotal['base_amount_currency'] += delta_base_currency  # REMOVED: causa doble conteo
                        # subtotal['base_amount'] += delta_base  # REMOVED: causa doble conteo

                        totals['tax_amount_currency'] += delta_tax_currency
                        totals['tax_amount'] += delta_tax
                        # totals['base_amount_currency'] += delta_base_currency  # REMOVED: causa doble conteo
                        # totals['base_amount'] += delta_base  # REMOVED: causa doble conteo

                cash_rounding_base_amount_currency = totals.get(
                    'cash_rounding_base_amount_currency', 0.0
                )
                cash_rounding_base_amount = totals.get(
                    'cash_rounding_base_amount', 0.0
                )
                totals['total_amount_currency'] = (
                    totals['base_amount_currency']
                    + totals['tax_amount_currency']
                    + cash_rounding_base_amount_currency
                )
                totals['total_amount'] = (
                    totals['base_amount']
                    + totals['tax_amount']
                    + cash_rounding_base_amount
                )
                # import wdb; wdb.set_trace();
                move.tax_totals = totals

    @api.onchange('invoice_date')
    def _onchange_currency_id(self):
        # Agregamos contexto para evitar la actualización de la tasa de cambio al validar la factura
        if not self.env.context.get('from_action_post', False):
            date_invoice = self.date or self.invoice_date or fields.Date.today()
            vals = {
                'is_multi_currency': False,
                'currency_rate': 1.0,
            }
            if self.currency_id:
                company = self.env.company
                company_currency = company.currency_id
                currency = self.currency_id
                if currency != company_currency:
                    curr_rate = currency.get_currency_rate(
                        company, date_invoice
                    )

                    vals['is_multi_currency'] = True
                    if currency.preciated:
                        vals['currency_rate'] = curr_rate.inverse_company_rate
                    else:
                        vals['currency_rate'] = curr_rate.company_rate
            self.write(vals)

            self._onchange_payment_term_date_invoice()

    @api.onchange('date')
    def _onchange_date(self):
        super()._onchange_date()
        for move in self:
            move._onchange_currency_id()
        return

    @api.onchange('currency_id')
    def _inverse_currency_id(self):
        currency_has_change = self._origin.currency_id != self.currency_id
        super()._inverse_currency_id()
        if (
            not self.env.context.get('force_rate', False)
            and currency_has_change
        ):
            for move in self:
                move._onchange_currency_id()
        return

    @api.onchange('invoice_payment_term_id', 'invoice_date')
    def _onchange_payment_term_date_invoice(self):
        date_invoice = self.invoice_date or fields.Date.context_today(self)
        if self.invoice_payment_term_id:
            pterm_lines_vals = (
                self.invoice_payment_term_id.with_context(
                    currency_id=self.company_id.currency_id.id
                )
                ._compute_terms(
                    date_ref=date_invoice,
                    currency=self.company_id.currency_id,
                    company=self.company_id,
                    tax_amount=1,
                    tax_amount_currency=1,
                    sign=1,
                    untaxed_amount=1,
                    untaxed_amount_currency=1,
                )
                .get('line_ids', [])
            )
            dates = [term['date'] for term in pterm_lines_vals]
            self.invoice_date_due = min(dates)
        elif self.invoice_date_due and (date_invoice > self.invoice_date_due):
            self.invoice_date_due = date_invoice

    @api.onchange('inform_period')
    def _onchange_inform_period(self):
        if self.inform_period:
            self.associated_inv_ids = False
        else:
            self.inform_period_date_from = False
            self.inform_period_date_to = False

    def _get_refund_common_fields(self):
        res = super()._get_refund_common_fields()
        res.append('currency_rate')
        return res

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
            pos_code.zfill(5) + '-' + move_code.zfill(8)
        )

    @api.depends('denomination', 'move_type', 'is_debit_note', 'is_FCE_invoice')
    def _compute_voucher_type_domain(self):
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

            sign = '>=' if inv.is_FCE_invoice else '<'
            threshold = f"{AFIP_FCE_CODE_START:03d}"
            domain.append(('afip_code', sign, threshold))
            inv.voucher_type_domain = json.dumps(domain)

    @api.onchange('voucher_type_id')
    def _set_is_FCE(self):
        self.is_FCE_invoice = False
        if int(self.voucher_type_id.afip_code) > AFIP_FCE_CODE_START:
            self.is_FCE_invoice = True

    @api.depends('invoice_line_ids', 'invoice_line_ids.price_unit')
    def _compute_amount_custom(self):
        def _filter_exempt(line):
            return any(line.tax_ids.mapped("is_exempt"))

        def _filter_untaxed(line):
            return not _filter_exempt(line) and not _filter_taxed(line)

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

    @api.onchange('associated_inv_ids')
    def _set_cn_dn_is_FCE(self):
        if self.is_debit_note or self.move_type == 'out_refund':
            are_FCE_invoices = self.associated_inv_ids.mapped('is_FCE_invoice')
            if len(are_FCE_invoices) > 1:
                raise UserError(
                    _(
                        "All associated invoices must be of the same type: FCE or non-FCE."
                    )
                )
            elif len(are_FCE_invoices) == 1:
                are_FCE_invoices = are_FCE_invoices[0]
                if are_FCE_invoices != self.is_FCE_invoice:
                    self.is_FCE_invoice = are_FCE_invoices
            elif len(are_FCE_invoices) == 0:
                self.is_FCE_invoice = False

    # --------------------------------------------------------------------------------
    # *********      MÉTODOS PARA PERCEPCIONES: *********
    @api.onchange('disable_perceptions')
    def _onchange_disable_perceptions(self):
        if self.disable_perceptions:
            self.perception_ids.unlink()
            self.invoice_line_ids.link_perception_to_move_lines()
            return {'value': {'disable_perceptions': True}}
        else:
            self._automatic_perception_calculation()
            return {'value': {'disable_perceptions': False}}

    @api.onchange(
        'invoice_date',
        'currency_id',
        'currency_rate',
        'invoice_line_ids',
    )
    def _automatic_perception_calculation(self):
        if self.is_sale_document() and not self.disable_perceptions:
            if self.partner_id:
                # Se agrupan las líneas de la factura sobre las cuales se aplican las percepciones
                # que corresponden (según concepto --> cuenta contable / posición fiscal --> partner)
                accounts = self.invoice_line_ids.mapped('account_id')
                perception_application_data = {}
                for account in accounts:
                    perceptions_applications = (
                        account.get_perceptions_applications(
                            self.partner_id.property_account_position_id
                        )
                    )
                    for application in perceptions_applications:
                        line_perception_application_data = (
                            application.get_perception_data(
                                self.partner_id, self.invoice_date
                            )
                        )
                        applicable = application.check_applicable(
                            destination_shipping=(
                                self.partner_shipping_id or self.partner_id
                            ),
                            source_shipping=self.company_id.partner_id,
                            sit_iibb=line_perception_application_data[
                                'sit_iibb'
                            ],
                            from_padron=line_perception_application_data[
                                'from_padron'
                            ],
                            excluded_percent=line_perception_application_data[
                                'excluded_percent'
                            ],
                        )
                        if applicable:
                            lines = self.invoice_line_ids.filtered(
                                lambda line: line.account_id == account
                            )
                            perception_application_data.setdefault(
                                application,
                                {'lines': self.env['account.move.line']},
                            )
                            perception_application_data[application].update(
                                line_perception_application_data
                            )
                            perception_application_data[application].update(
                                {
                                    'lines': perception_application_data[
                                        application
                                    ]['lines']
                                    + lines
                                }
                            )

                perception_tax_line_vals = []
                # Se calculan las percepciones obtenidas anteriormente y se generan los correspondientes
                # dicts de datos para crear las líneas de percepción.
                for application in perception_application_data.keys():
                    application_data = perception_application_data[application]
                    application_data['currency_rate'] = self.currency_rate
                    base, amount = application.apply_perception(
                        application_data
                    )
                    if base > 0 and amount > 0:
                        perception_tax_line_vals.append(
                            {
                                'name': application.perception_tax_id.name,
                                'date': self.invoice_date,
                                'invoice_id': self.id,
                                'partner_id': self.partner_id.id,
                                'base': base,
                                'amount': amount,
                                'perception_id': application.perception_tax_id.id,
                                'manual': False,
                                'tax_app_id': application.id,
                                'reg_code': application.reg_code,
                                'concept_id': application.concept_id.id,
                            }
                        )
                # Se buscan las percepciones configuradas por código python que aplican según la posición
                # fiscal del partner. La aplicación o no y su cálculo se definen en dicho código.
                for (
                    perception
                ) in self.partner_id.get_python_application_perceptions():
                    perceptions_applications = (
                        perception.calculate_python_custom_tax(
                            self.partner_id, self
                        )
                    )
                    for application in perceptions_applications:
                        base = application['base']
                        amount = application['amount']
                        if base > 0 and amount > 0:
                            perception_tax_line_vals.append(
                                {
                                    'name': perception.name,
                                    'date': self.invoice_date,
                                    'invoice_id': self.id,
                                    'partner_id': self.partner_id.id,
                                    'base': base,
                                    'amount': amount,
                                    'perception_id': perception.id,
                                    'manual': False,
                                    'reg_code': application.get(
                                        'reg_code', False
                                    ),
                                    'concept_id': application.get(
                                        'concept_id', False
                                    ),
                                }
                            )

                # Se generan las líneas de percepción y se asocian a la factura
                new_perception_lines = self.env['perception.tax.line']
                for perception_tax_line_vals in perception_tax_line_vals:
                    new_perception_lines += self.env['perception.tax.line'].new(
                        perception_tax_line_vals
                    )
                self.perception_ids = new_perception_lines
            else:
                self.perception_ids.unlink()
            # Una vez creadas / eliminadas las líneas de percepción, se actualizan los montos de las líneas
            # contables que corresponden a cada percepción con los montos correctos calculados.
            self.invoice_line_ids.link_perception_to_move_lines()

    def _get_perception_manual_base(self):
        return sum(
            self.invoice_line_ids.filtered(
                lambda line: line.tax_ids
                and (True not in line.tax_ids.mapped('is_exempt'))
            ).mapped('price_subtotal')
        )

    @api.onchange('perception_ids', 'invoice_line_ids')
    def _onchange_perception_ids(self):
        if self.is_purchase_document(include_receipts=True) or (
            self.is_sale_document(include_receipts=True)
            and self.disable_perceptions
        ):
            base = self._get_perception_manual_base()
            if base > 0:
                self.perception_ids.autocomplete_base_amount(base)
            else:
                self.perception_ids.unlink()
            self.invoice_line_ids.link_perception_to_move_lines()
            self.with_context(
                skip_invoice_line_sync=True
            )._update_perception_move_line_amount()

    def _update_perception_move_line_amount(self):
        for perception in self.perception_ids.mapped('perception_id'):
            perception_lines = self.line_ids.filtered(
                lambda line: line.tax_line_id == perception
            )
            for perception_line in perception_lines:
                amount = sum(
                    self.perception_ids.filtered(
                        lambda line: line.perception_id == perception
                    ).mapped('amount')
                )
                amount_currency = amount
                if self.is_multi_currency:
                    amount = sum(
                        self.perception_ids.filtered(
                            lambda line: line.perception_id == perception
                        ).mapped('amount_secondary_currency')
                    )
                sign = -1 if perception_line.balance < 0 else 1
                perception_line.write(
                    {
                        'balance': sign * amount,
                        'amount_currency': sign * amount_currency,
                    }
                )

    def add_perceptions(self):
        for move in self:
            move._automatic_perception_calculation()
            move._update_perception_move_line_amount()

    def _set_perception_date(self):
        """
        Usamos la date de la invoice porque en el caso de facturas de proveedor que son ingresadas en el mes
        siguiente, la invoice_date no nos serviría a la hora de cerrar los impuestos del  mes. Ej, si la
        factura es del 29/3/24 (invoice_date) y se ingresa el 1/4/24 (date) porque el proveedor la entregó
        tarde, esta percepción no saldría en el archivo de percepciones generado para Abril.
        """
        invoices = self.filtered(lambda move: move.is_invoice())
        for inv in invoices:
            for perc_line in inv.perception_ids:
                if not perc_line.date:
                    perc_line.write({'date': inv.date})

    def _get_perceptions_ctx(self):
        """
        Return values to compute perception in python code field
        """
        # TODO: Define values
        return {
            'invoice_date': self.invoice_date,
            'amount_untaxed': self.amount_untaxed,
            'currency_rate': self.currency_rate,
        }

    # --------------------------------------------------------------------------------
    # *********      FIN MÉTODOS PARA PERCEPCIONES *********

    # --------------------------------------------------------------------------------
    # *********      MÉTODOS PARA IMPUESTOS INTERNOS: *********
    @api.onchange('invoice_line_ids')
    def _automatic_internal_taxes_calculation(self):
        if self.is_sale_document():
            amount = 0.0
            base = 0.0
            groups = (self.tax_totals or {}).get('groups_by_subtotal') or {}
            for taxes in groups.values():
                for tax in taxes:
                    group = self.env['account.tax.group'].browse(
                        tax.get('tax_group_id')
                    )
                    if group.group_type == 'internals':
                        amount = tax.get('tax_group_amount', 0.0) or amount
                        base = tax.get('tax_group_base_amount', 0.0) or base
            if amount > 0:
                # Se generan las líneas de impuestos internos y se asocian a la factura
                internal_tax_group = self.env['account.tax.group'].search(
                    [('group_type', '=', 'internals')]
                )
                internal_taxes = self.env['account.tax'].search(
                    [
                        ('company_id', '=', self.company_id.id),
                        ('type_tax_use', '=', 'sale'),
                        ('tax_group_id', '=', internal_tax_group.id),
                    ],
                    limit=1,
                )
                self.internal_taxes_ids = self.env['internal.tax.line'].new(
                    {
                        'invoice_id': self.id,
                        'base': base,
                        'amount': amount,
                        'tax_id': internal_taxes.id,
                        'manual': False,
                    }
                )
            else:
                self.internal_taxes_ids = False
        self._link_internal_taxes()

    @api.onchange('internal_taxes_ids')
    def _link_internal_taxes(self):
        if self.is_purchase_document():
            self.invoice_line_ids.link_internal_taxes_to_move_lines(
                self.internal_taxes_ids.mapped('tax_id')
            )
            self.with_context(
                skip_invoice_line_sync=True
            )._update_internal_taxes_move_line_amount()

    def _update_internal_taxes_move_line_amount(self):
        for internal_tax in self.internal_taxes_ids.mapped('tax_id'):
            internal_tax_line = self.line_ids.filtered(
                lambda line: line.tax_line_id == internal_tax
            )
            amount = sum(
                self.internal_taxes_ids.filtered(
                    lambda line: line.tax_id == internal_tax
                ).mapped('amount')
            )
            amount_currency = amount
            # if self.is_multi_currency:
            #     amount = sum(
            #         self.internal_taxes_ids.filtered(
            #             lambda line: line.tax_id == internal_tax
            #         ).mapped('amount_secondary_currency')
            #     )
            sign = -1 if internal_tax_line.balance < 0 else 1
            internal_tax_line.write(
                {
                    'balance': sign * amount,
                    'amount_currency': sign * amount_currency,
                }
            )

    # --------------------------------------------------------------------------------
    # *********      FIN MÉTODOS PARA IMPUESTOS INTERNOS *********

    def _get_fce_prefix(self):
        voucher_type = int(self.voucher_type_id.afip_code)
        if voucher_type in [
            int(
                self.env.ref(
                    'l10n_ar_eynes.factura_credito_electronica_a'
                ).afip_code
            ),
            int(
                self.env.ref(
                    'l10n_ar_eynes.factura_credito_electronica_b'
                ).afip_code
            ),
        ]:
            return 'FCE'
        elif voucher_type in [
            int(
                self.env.ref(
                    'l10n_ar_eynes.nota_credito_electronica_a'
                ).afip_code
            ),
            int(
                self.env.ref(
                    'l10n_ar_eynes.nota_credito_electronica_b'
                ).afip_code
            ),
        ]:
            return 'NCE'
        elif voucher_type in [
            int(
                self.env.ref(
                    'l10n_ar_eynes.factura_debito_electronica_a'
                ).afip_code
            ),
            int(
                self.env.ref(
                    'l10n_ar_eynes.factura_debito_electronica_b'
                ).afip_code
            ),
        ]:
            return 'NDE'
        return ''

    def _required_supplier_move_reference(self):
        """Supplier bills must have an supplier_move_reference set to be posted"""
        for record in self:
            if (
                record.is_purchase_document()
                and not record.supplier_move_reference
            ):
                raise ValidationError(
                    _("You must complete supplier move reference.")
                )

    def _post(self, soft=True):
        self._required_supplier_move_reference()
        for move in self:
            move.validate_period()
            if move.is_sale_document() and move.id:
                move.validate_denomination()

        sale_invoices = self.filtered(lambda move: move.is_sale_document())
        electronic_invoices = sale_invoices.filtered(
            lambda move: move.fiscal_type == 'electronic'
        )
        for inv in sale_invoices - electronic_invoices:
            if not inv.posted_before:
                sequence = inv.journal_id.get_sequence_from_invoice(inv)._next()
                if inv.is_FCE_invoice:
                    sequence = inv._get_fce_prefix() + sequence
                inv.write({'internal_number': sequence})

        posted_moves = super()._post(soft=soft)
        posted_moves._set_perception_date()

        return posted_moves

    def action_post(self):
        invalid_moves = self.filtered(
            lambda move: move.move_type in ('out_invoice', 'out_refund')
            and move.amount_total == 0
        )
        if invalid_moves:
            raise ValidationError(_('The amount to validate cannot be $0.'))

        sale_invoices = self.filtered(lambda move: move.is_sale_document())
        electronic_invoices = sale_invoices.filtered(
            lambda move: move.fiscal_type == 'electronic'
        )

        super(AccountMove, self - electronic_invoices).action_post()

        # Agregamos contexto para evitar la actualización de la tasa de cambio al validar la factura
        return electronic_invoices.with_context(
            from_action_post=True
        )._validate_electronic_invoices()

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

    def copy_data(self, default=None):
        data_list = super().copy_data(default)
        for move, data in zip(self, data_list):
            if move.move_type in ('out_invoice', 'in_invoice'):
                data['perception_ids'] = [
                    (command, _id, line_vals)
                    for command, _id, line_vals in data['perception_ids']
                    if command == Command.CREATE
                ]
        return data_list

    def unlink(self):
        """
        Unlink moves was moved to api.ondelete method
        """
        return super().unlink()

    @api.ondelete(at_uninstall=False)
    def _check_electronic_invoice_unlink(self):
        if self._check_electronic_invoice_informed_before():
            raise UserError(
                _(
                    "You can't delete an electronic invoice that was sent to AFIP."
                    "If you have any problems, please contact our support service."
                )
            )

    def _check_closed_journal_moves(self):
        closed_journal_moves = self.filtered(
            lambda move: (
                move.date < move.journal_id.due_date
                if move.journal_id.due_date
                else False
            )
        )

        if closed_journal_moves:
            message = _("Moves before journal due date can't be cancelled.\n")
            journals = closed_journal_moves.mapped('journal_id')
            for journal in journals:
                message += _(
                    'Journal: %(journal_name)s --> %(date)s',
                    journal_name=journal.name,
                    date=journal.due_date,
                )
            raise ValidationError(message)
        return True

    def button_cancel(self):
        self._check_closed_journal_moves()

        if self._check_electronic_invoice_approved_before():
            raise UserError(
                _(
                    "You can't cancel an electronic invoice that seems to be informed to AFIP. "
                    "Try to syncronize it using the wizard from Action menu."
                )
            )

        return super().button_cancel()

    def button_draft(self):
        self._check_closed_journal_moves()

        if self._check_electronic_invoice_approved_before():
            raise UserError(
                _(
                    "You can't set to Draft an electronic invoice that seems to be informed to AFIP. "
                    "Try to syncronize it using the wizard from Action menu."
                )
            )

        return super().button_draft()

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
            move.show_reset_to_draft_button = (
                False
                if move._check_electronic_invoice_approved_before()
                else True
            )
        return

    @api.model_create_multi
    def create(self, vals):
        res = super().create(vals)
        for move in res:
            if move.is_invoice():
                if not move.invoice_date:
                    move.write(
                        {'invoice_date': fields.Date.context_today(self)}
                    )
                if not move.denomination:
                    if move.is_sale_document():
                        denomination = move.journal_id.denomination
                    else:
                        denomination = (
                            move.partner_id.property_account_position_id.supplier_denomination
                        )
                    move.write({'denomination': denomination})
        return res

    def are_sale_documents(self):
        return all(move.is_sale_document() for move in self)

    def are_purchase_documents(self):
        return all(move.is_purchase_document() for move in self)

    def _action_register_multi_payments(self, partners, view_id, context):
        payment_orders = self.env['account.payment.order']
        for partner in partners:
            invoices = self.filtered(lambda move: move.partner_id == partner)
            po = self.env['account.payment.order'].create(
                invoices._get_payment_order_vals()
            )
            payment_orders += po

        return {
            'name': _('Register Payment'),
            'res_model': 'account.payment.order',
            'domain': [('id', 'in', payment_orders.ids)],
            'view_mode': 'tree',
            'views': [
                [
                    self.env.ref(
                        'l10n_ar_eynes.account_payment_order_view_tree'
                    ).id,
                    'list',
                ],
                [view_id.id, 'form'],
            ],
            'target': 'current',
            'context': context,
            'type': 'ir.actions.act_window',
        }

    def action_register_payment(self):
        '''Open the account.payment.register wizard to pay the selected journal entries.
        :return: An action opening the account.payment.register wizard.
        '''
        view_id = self.env.ref(
            'l10n_ar_eynes.account_supplier_payment_order_view_form'
        )
        context = self.env.context.copy()
        if self.are_sale_documents():
            view_id = self.env.ref(
                'l10n_ar_eynes.account_customer_payment_order_view_form'
            )
            context.update(
                {
                    'default_type': 'receipt',
                }
            )
        elif not self.are_purchase_documents():
            raise UserError(
                _(
                    "You can only register payments for customers or suppliers at the same time."
                )
            )

        try:
            self.ensure_one()
        except ValueError:
            partners = self.mapped('partner_id')
            if len(partners) > 1:
                return self._action_register_multi_payments(
                    partners, view_id, context
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
        debt_line_ids = []
        income_line_ids = []
        for invoice in self:
            move_line_domain = [
                ('id', 'in', invoice.line_ids.ids),
                ('reconciled', '=', False),
            ]
            if invoice.move_type in ['out_refund', 'in_invoice']:
                move_line_domain += [
                    ('debit', '=', 0),
                    ('credit', '>', 0),
                ]
                add_to = debt_line_ids
            elif invoice.move_type in ['out_invoice', 'in_refund']:
                move_line_domain += [
                    ('debit', '>', 0),
                    ('credit', '=', 0),
                ]
                add_to = income_line_ids

            move_lines = self.env['account.move.line'].search(move_line_domain)

            for move_line in move_lines:
                add_to.append(
                    (
                        0,
                        0,
                        {
                            'invoice_id': invoice.id,
                            'move_line_id': move_line.id,
                            'account_id': move_line.account_id.id,
                            'original_currency_id': move_line.company_id.currency_id.id,
                            'currency_id': move_line.currency_id.id,
                        },
                    )
                )

        _type = 'receipt' if self.are_sale_documents() else 'payment'
        po_vals = {
            'type': _type,
            'partner_id': invoice.partner_id.id,
            'journal_id': invoice._get_payment_order_journal(_type).id,
            'currency_id': invoice.currency_id.id,
            'debt_line_ids': debt_line_ids,
            'income_line_ids': income_line_ids,
        }

        if invoice.currency_id != invoice.company_id.currency_id:
            po_vals['payment_rate'] = invoice.currency_rate

        if self.are_sale_documents():
            po_vals['disable_retentions'] = True

        return po_vals

    def _get_payment_order_journal(self, journal_type):
        domain = [('type', '=', journal_type)]
        if self.is_multi_currency and self.currency_id != self.env.ref(
            'base.ARS'
        ):
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

    def _reverse_move_vals(self, default_values, cancel=True):
        vals = super()._reverse_move_vals(default_values, cancel=cancel)

        perceptions = []
        for p in self.perception_ids:
            perceptions.append(
                (
                    0,
                    0,
                    {
                        'amount': p.amount,
                        'base': p.base,
                        'concept_id': p.concept_id.id,
                        'manual': p.manual,
                        'name': p.name,
                        'partner_id': p.partner_id.id,
                        'perception_id': p.perception_id.id,
                        'reg_code': p.reg_code,
                        'tax_app_id': p.tax_app_id.id,
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

    def _get_mail_template(self):
        """
        @override --> Custom PDF inyection
        :return: the correct mail template based on the current move type
        """
        report = (
            'l10n_ar_eynes.email_template_edi_credit_note'
            if all(move.move_type == 'out_refund' for move in self)
            else 'l10n_ar_eynes.email_template_edi_invoice'
        )
        return report

    def _get_name_invoice_report(self):
        """This method need to be inherit by the localizations if they want to
        print a custom invoice report instead of
        the default one. For example please review the l10n_ar module"""
        self.ensure_one()
        if self.fiscal_type == 'electronic':
            return 'l10n_ar_eynes.account_move_report'
        return super()._get_name_invoice_report()

    def get_invoice_pdf_report_attachment(self):
        if self.fiscal_type == 'electronic':
            if len(self) < 2 and self.invoice_pdf_report_id:
                # if the Send & Print succeeded
                return (
                    self.invoice_pdf_report_id.raw,
                    self.invoice_pdf_report_id.name,
                )
            elif len(self) < 2 and self.message_main_attachment_id:
                # if the Send & Print failed with fallback=True -> proforma PDF
                return (
                    self.message_main_attachment_id.raw,
                    self.message_main_attachment_id.name,
                )
            # all other cases
            pdf_content = self.env['ir.actions.report']._render(
                'l10n_ar_eynes.account_move_report', self.ids
            )[0]
            pdf_name = (
                self._get_invoice_report_filename()
                if len(self) == 1
                else "Invoices.pdf"
            )
            return pdf_content, pdf_name
        else:
            return super().get_invoice_pdf_report_attachment()

    def action_invoice_print(self):
        """
        @override --> Custom PDF inyection
        Print the invoice and mark it as sent, so that we can see more
        easily the next step of the workflow
        """
        super().action_invoice_print()
        return self.env.ref(self._get_name_invoice_report()).report_action(self)

    def get_afip_logo_path(self):
        return "l10n_ar_eynes/static/img/ARCA_logo.png"

    def get_afip_logo(self):
        return b64encode(file_open(self.get_afip_logo_path(), 'rb').read())

    def price_subtotal_to_PDF(self):
        price_subtotal = self.amount_untaxed
        if self.denomination == 'b':
            price_subtotal += self.amount_tax
        return price_subtotal

    def _report_xls_query_extra(self):
        """
        Método útil para extender el alcance del reporte por jurisdicciones export.sales.by.jurisdiction.xls
        """
        select_extra = """ """
        join_extra = """ """
        where_extra = """ """
        sort_selection = """ """
        return (select_extra, join_extra, where_extra, sort_selection)

    def get_sale_orders_name(self):
        self.ensure_one()
        return self.invoice_origin

    # --------------------------------------------------------------------------------
    # *********      MÉTODOS PARA OBTENER MONTOS SEGÚN TIPO DE IVA: *********
    def get_amounts_by_vat_aliquot(self, aliquot, currency='company'):
        """
        Returns a dictionary with the amounts of the invoice grouped by tax type.
        :param aliquot: string or float representing the aliquot type, can be 'no_taxed', 'exempt', 0.0,
            '0.0', 10.5, 21.0, 27.0, 5.0, '2.5', etc.
        :param currency: 'company' for company currency (ARS), 'invoice' for invoice currency
        :return: dict with amounts for 'base' and 'tax'
        """
        self.ensure_one()

        amounts = {'base': 0.0, 'tax': 0.0}

        # Map aliquot values to their float equivalents
        aliquot_map = {
            'exempt': 'exempt',
            'no_taxed': 'no_taxed',
            '0.0': 0.0,
            0.0: 0.0,
            '10.5': 10.5,
            10.5: 10.5,
            '21.0': 21.0,
            '21': 21.0,
            21: 21.0,
            '27.0': 27.0,
            '27': 27.0,
            27: 27.0,
            '5.0': 5.0,
            '5': 5.0,
            5: 5.0,
            '2.5': 2.5,
            2.5: 2.5,
        }
        val = aliquot_map.get(aliquot, aliquot)

        if val == 'exempt':
            amounts['base'] = (
                self.amount_exempt_cur
                if currency == 'invoice'
                else self.amount_exempt
            )
        elif val == 'no_taxed':
            amounts['base'] = (
                self.amount_no_taxed_cur
                if currency == 'invoice'
                else self.amount_no_taxed
            )
        elif val == 0.0:
            for line in self.invoice_line_ids:
                for tax in line.tax_ids:
                    if (
                        tax.tax_group_id.group_type == 'vat'
                        and tax.amount == 0.0
                    ):
                        amounts['base'] += (
                            line.price_subtotal
                            if currency == 'invoice'
                            else line.balance
                        )
        elif isinstance(val, float):
            # For aliquots with a numeric value (VAT rates)
            tax_line = self.line_ids.filtered(
                lambda line: line.tax_line_id and line.tax_line_id.amount == val
            )
            if currency == 'company':
                amounts['tax'] += sum(abs(line.balance) for line in tax_line)
                amounts['base'] += sum(
                    line.tax_base_amount for line in tax_line
                )
            else:
                amounts['tax'] += sum(
                    abs(line.amount_currency) for line in tax_line
                )
            for line in self.invoice_line_ids:
                for tax in line.tax_ids:
                    if tax.amount == val:
                        amounts['base'] += line.price_subtotal
        return amounts

    # --------------------------------------------------------------------------------
    # *********     FIN MÉTODOS PARA OBTENER MONTOS SEGÚN TIPO DE IVA *********

    # --------------------------------------------------------------------------------
    # *********      MÉTODOS PARA FACTURA ELECTRÓNICA (ARCA): *********
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

        ctx = self.env.context.copy()
        ctx['company_id'] = company.id

        wsfe_conf = WSFEConfig.with_context(**ctx).get_config()

        if local_list[0]:
            return wsfe_conf
        wsfex_conf = WSFEXConfig.with_context(**ctx).get_config()
        return wsfex_conf

    def _check_fce_using_abc(self, amount_total):
        if not self.partner_id:
            return False
        if not self.partner_id.vat:
            return False
        if (
            self.is_debit_note or self.move_type == 'out_refund'
        ) and self.associated_inv_ids.filtered(lambda inv: inv.is_FCE_invoice):
            _logger.info('The Invoice ID: %s must be of type FCRED' % self.id)
            return True
        else:
            is_bc = (
                self.env['afip.big.company']
                .sudo()
                .search([('cuit', '=like', self.partner_id.vat)])
            )
            if is_bc and amount_total >= self.company_id.fcred_minimum_amount:
                _logger.info(
                    'The Invoice ID: %s must be of type FCRED' % self.id
                )
                return True
        return False

    def _check_fce_using_ws(self, amount_total):
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
        if amount and amount_total >= amount:
            return True
        return False

    def _check_must_be_fce(self):
        """
        If the invoice matches some criteria, the invoice must be -FCE-
        """
        res = False
        if (
            self.is_sale_document()
            and self.company_id.fcred_is_fce_emitter
            and self.fiscal_type == 'electronic'
        ):
            amount_total = (
                self.amount_total
                if self.currency_id == self.company_currency_id
                else self.amount_total_cur
            )
            try:
                res = self._check_fce_using_ws(amount_total)
            except Exception:
                _logger.warning('WSFECRED Fail.. trying old method..')
                res = self._check_fce_using_abc(amount_total)

        return res

    def _force_voucher_type(self):
        for move in self:
            domain = move.voucher_type_domain or []
            if isinstance(domain, str):
                try:
                    domain = safe_eval(domain)
                except Exception:
                    _logger.warning(
                        "Invalid voucher_type_domain on move %s: %s",
                        move.display_name,
                        move.voucher_type_domain,
                    )
                    domain = []
            move.voucher_type_id = self.env['res.voucher.type'].search(
                domain, limit=1
            )

    def _ensure_fce_values(self):
        """
        If invoice must be of type FCE, ensure certain values are set.
        """
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
        # Ensure Fiscal Type FCE
        self.is_FCE_invoice = True
        self._compute_voucher_type_domain()
        self._force_voucher_type()

        if not self.optional_ids:
            conf = self._get_ws_conf()
            aios = []
            if self.is_debit_note or self.move_type == 'out_refund':
                aio = self.env['ws.optionals'].search(
                    [
                        ('code', '=', '22'),
                        ('wsfe_config_id', '=', conf.id),
                    ]
                )
                dd = {
                    'optional_id': aio.id,
                    'value': 'N',
                }
                aios.append((0, 0, dd))
            # Optionals
            else:
                aio_todo = self.env['ws.optionals'].search(
                    [
                        ('code', 'in', ('2101', '27')),
                        ('wsfe_config_id', '=', conf.id),
                    ]
                )
                # 2101: cbu del emisor, 27 sca|adc
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

    def _clean_fce_values(self):
        self.is_FCE_invoice = False
        self._compute_voucher_type_domain()
        self._force_voucher_type()
        self.optional_ids.unlink()

    def _create_ws_request(self):
        request = self.env['ws.request'].create(
            {
                'nregs': len(self),
            }
        )
        return request.id

    def _check_electronic_invoice_informed_before(self):
        if self.env['ws.request.detail'].search(
            [
                ('invoice_id', 'in', self.ids),
            ]
        ):
            return True
        return False

    def _check_electronic_invoice_approved_before(self):
        if self.filtered(
            lambda move: move.is_sale_document(include_receipts=True)
            and move.fiscal_type == 'electronic'
            and (move.cae or move.cae_due_date)
        ):
            return True
        return bool(self._get_ws_request_details_with_data())

    def _get_ws_request_details_with_data(self):
        return self.env['ws.request.detail'].search(
            [
                ('invoice_id', 'in', self.ids),
                ('result', 'in', ('A', 'P')),
            ]
        )

    def _validate_electronic_invoices(self, soft=False):
        if self:
            request_id = self._create_ws_request()
            ws = self._get_ws_conf()
            posted_moves = self.env['account.move']
            for inv in self:
                if inv._check_electronic_invoice_approved_before():
                    _logger.info("Invoice informed before.")
                    ws_requests = inv._get_ws_request_details_with_data()
                    syncronized = False
                    for req in ws_requests:
                        if req.voucher_number > 0 and not syncronized:
                            context = self.env.context.copy()
                            context['active_id'] = inv.id
                            context['from_validate_button'] = True
                            context['ws_id'] = ws.id
                            sync_wiz = (
                                self.env['afip.sinchronize.voucher']
                                .with_context(**context)
                                .create(
                                    {
                                        'pos_id': inv.journal_id.id,
                                        'voucher_number': req.voucher_number,
                                    }
                                )
                            )
                            sync_wiz._compute_sync_values()
                            try:
                                sync_wiz.relate_invoice()
                                posted_moves += inv
                                syncronized = True
                            except UserError:
                                _logger.error(sync_wiz.error_msg)
                else:
                    if inv._check_must_be_fce():
                        inv._ensure_fce_values()
                    elif inv.is_FCE_invoice:
                        inv._clean_fce_values()
                    try:
                        ws.send_invoice_to_afip(inv, request_id)
                    except Exception:
                        _logger.error(
                            _("Error with AFIP trying to validate invoice.")
                        )
                    else:
                        posted = inv._post(soft=soft)
                        if posted:
                            posted_moves += posted

            errors = self - posted_moves
            if errors:
                request = self.env['ws.request'].browse(request_id)
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
        if self.fiscal_type == 'electronic':
            ws_conf = self._get_ws_conf()
            ws_pos = ws_conf.point_of_sale_ids.filtered(
                lambda pos: pos.journal_id == self.journal_id
            )
            return int(ws_pos.code)
        return self.journal_id.get_pos_number()

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
            name = '%05d-%08d' % (pos, number)
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
            if inv.state == 'draft':
                inv._post(soft=False)
            return

    def get_arca_currency_rate(self):
        """Button to get legal currency rate to electronic invoice informed to ARCA"""
        if self:
            request_id = self._create_ws_request()
            ws = self._get_ws_conf()

            result, error_msg = ws.get_currency_rate(self, request_id)

            if result:
                self.currency_rate = result
                return True
            else:
                context = dict(self._context or {})
                context["message"] = _(
                    "Error trying to get currency rate of %(currency)s on %(date)s.\n"
                    "Error received -> %(error_msg)s",
                    currency=self.currency_id.name,
                    date=self.invoice_date,
                    error_msg=error_msg,
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

    def delete_all_requests(self):
        for move in self:
            for request in move.ws_request_ids:
                request.unlink()

    # --------------------------------------------------------------------------------
    # *********     FIN MÉTODOS PARA FACTURA ELECTRÓNICA (ARCA) *********
