import base64
import binascii
import codecs
import io
import json
import logging
import tempfile
from calendar import monthrange
from openpyxl import Workbook

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class LibroIVAExporterWizard(models.TransientModel):
    _name = 'libro.iva.exporter.wizard'
    _description = 'Libro IVA Digital Exporter Wizard'

    date_from = fields.Date(required=True)
    date_to = fields.Date(required=True)
    company_id = fields.Many2one('res.company', 'Company', required=True)
    company_id_domain = fields.Char(
        default=lambda self: self._default_company_ids()
    )
    is_simple_vat = fields.Boolean('Is Simple VAT?', default=False)
    notes = fields.Text('Notes', readonly=True)
    state = fields.Selection(
        [('init', 'Start'), ('done', 'Done')], 'State', default='init'
    )
    file_format = fields.Selection(
        [('txt', 'TXT'), ('xlsx', 'XLSX')],
        string='File Format',
        default='txt',
        required=True,
    )

    @api.model
    def _default_company_ids(self):
        return json.dumps(
            [('id', 'in', self.env.context.get('allowed_company_ids', []))]
        )

    def _check_date_to(self):
        end_of_month = monthrange(self.date_from.year, self.date_from.month)[1]
        limit = self.date_from.replace(day=end_of_month)
        if self.date_to > limit:
            raise UserError(_('Date to must be less or equal than %s') % limit)

    # METHODS TO GET NEEDED FIELDS:
    def _get_invoice_tax_lines(self, invoice):
        tax_line_ids = invoice.line_ids.filtered(lambda line: line.tax_line_id)
        return tax_line_ids

    def _get_invoice_not_vat_tax_lines(self, invoice):
        tax_line_ids = self._get_invoice_tax_lines(invoice).filtered(
            lambda line: line.tax_line_id.tax_group_id.group_type != 'vat'
        )
        return tax_line_ids

    def _get_invoice_vat_tax_lines(self, invoice):
        tax_line_ids = self._get_invoice_tax_lines(invoice).filtered(
            lambda line: line.tax_line_id.tax_group_id.group_type == 'vat'
        )
        return tax_line_ids

    def _get_perception_with_type(self, invoice, jurisdiction_or_type):
        amount = 0.0
        for perception_id in invoice.perception_ids:
            if (
                perception_id.perception_id.jurisdiccion == jurisdiction_or_type
                or perception_id.perception_id.retention_type
                == jurisdiction_or_type
            ):
                amount += perception_id.amount
        return ('%016.2f' % amount).replace('.', '')

    def _get_taxes_with_type(self, invoice, fee_type):
        amount = 0.0
        for tax_id in self._get_invoice_tax_lines(invoice):
            if tax_id.tax_line_id.tax_group_id.group_type == fee_type:
                amount += tax_id.price_total
        return ('%016.2f' % amount).replace('.', '')

    def _get_taxes_with_type_others(self, invoice):
        amount = 0.0
        for tax_id in self._get_invoice_tax_lines(invoice):
            if tax_id.tax_line_id.tax_group_id.group_type == 'others':
                amount += tax_id.price_total
        for perception_id in invoice.perception_ids:
            if perception_id.perception_id.retention_type == 'other':
                amount += perception_id.amount
        return ('%016.2f' % amount).replace('.', '')

    def _get_operation_code(self, invoice):
        if invoice.iva_digital_operation_code == 'NC':
            return ' '
        return invoice.iva_digital_operation_code

    def _get_tax_lines_qty(self, invoice):
        qty = 0
        if invoice.denomination in ['C']:
            return u'{}'.format(qty)
        qty += len(
            invoice.invoice_line_ids.mapped('tax_ids')
            .filtered(lambda tax: tax.tax_group_id.group_type == 'vat')
            .ids
        )
        return u'{}'.format(qty) if qty < 10 else False

    def _get_amount_original_currency(self, invoice, amount, amount_cur):
        return ('%016.2f' % amount).replace('.', '')

    def _get_fiscal_credit_currency(self, invoice):
        cfc = 0
        for tax_line in self._get_invoice_vat_tax_lines(invoice):
            cfc += abs(tax_line.amount_currency)
        return cfc

    def _get_invoice_date(self, invoice, errors):
        try:
            date = invoice.invoice_date.strftime('%Y%m%d')
        except Exception as e:
            _logger.error(
                'Error on field %s: %s' % ('account_move.invoice_date', e)
            )
            date = False
            errors.append(
                _(
                    'Invoice %(name)s of %(type)s: Wrong %(field)s',
                    name=invoice.name,
                    type=(
                        _('suppliers')
                        if invoice.move_type.startswith('in_')
                        else _('customers')
                    ),
                    field=self.env['account.move']
                    ._fields['invoice_date']
                    .string,
                )
            )
        return date

    def _get_invoice_voucher_type(self, invoice, errors):
        try:
            if not invoice.voucher_type_id:
                raise ValueError('User must enter voucher type')
            voucher_type = '%.3s' % str(
                invoice.voucher_type_id.afip_code
            ).rjust(3, '0')
        except Exception as e:
            _logger.error(
                'Error on field %s: %s' % ('account_move.voucher_type_id', e)
            )
            voucher_type = False
            errors.append(
                _(
                    'Invoice %(name)s of %(type)s: Wrong %(field)s in Voucher Type or it is not selected',
                    name=invoice.name,
                    type=(
                        _('suppliers')
                        if invoice.move_type.startswith('in_')
                        else _('customers')
                    ),
                    field=self.env['res.voucher.type']
                    ._fields['afip_code']
                    .string,
                )
            )
        return voucher_type

    def _get_invoice_point_of_sale(self, invoice, errors):
        try:
            if invoice.is_sale_document():
                pos = '%.5s' % str(invoice.get_pos()).rjust(5, '0')
                invoice_name = invoice.internal_number
            else:
                invoice_name = invoice.supplier_move_reference
            if not invoice_name:
                invoice_name = "/"
            if invoice.is_purchase_document() or 'False' in pos:
                if '-' in invoice_name:
                    pos = '%.5s' % str(invoice_name.split('-')[0]).rjust(5, '0')
                    pos = pos if pos.isdigit() else '00000'
                else:
                    pos = '00000'
        except Exception as e:
            _logger.error(
                'Error on field %s: %s' % ('account_move.journal_id.code', e)
            )
            pos = False
            errors.append(
                _(
                    'Invoice %(name)s (ID %(id)s) of %(type)s: Wrong %(field)s in Journal',
                    name=invoice.name,
                    id=invoice.id,
                    type=(
                        _('suppliers')
                        if invoice.move_type.startswith('in_')
                        else _('customers')
                    ),
                    field=self.env['account.journal']._fields['code'].string,
                )
            )
        return pos

    def _get_invoice_number(self, invoice, errors):
        import_clearance = ''.rjust(16, ' ')
        if invoice.is_sale_document():
            internal_number = invoice.internal_number
        else:
            internal_number = invoice.supplier_move_reference
        if not internal_number:
            internal_number = "/"
        if invoice.iva_digital_operation_code in ['X', 'Z']:
            import_clearance = internal_number.rjust(16, ' ')
            internal_number = '0'
        else:
            if internal_number and '-' in internal_number:
                internal_number = internal_number.split('-')[1]
            try:
                int(internal_number)
            except Exception as e:
                internal_number = '0'
                _logger.error(
                    'Error on field %s: %s'
                    % ('account_move.internal_number', e)
                )
                errors.append(
                    _(
                        'Invoice %(name)s (ID %(id)s) of %(type)s: Wrong %(field)s',
                        name=invoice.name,
                        id=invoice.id,
                        type=(
                            _('suppliers')
                            if invoice.move_type.startswith('in_')
                            else _('customers')
                        ),
                        field=self.env['account.move']
                        ._fields['internal_number']
                        .string,
                    )
                )
        internal_number = '%.20s' % internal_number.rjust(20, '0')
        return internal_number, import_clearance

    def _get_partner_doc_type(self, invoice, errors):
        try:
            partner_document_type = '%.2s' % str(
                invoice.partner_id.document_type_id.afip_code
            ).rjust(2, '0')
        except Exception as e:
            _logger.error(
                'Error on field %s: %s'
                % ('account_move.partner_id.document_type_id', e)
            )
            partner_document_type = False
            errors.append(
                _(
                    'Invoice %(name)s (ID %(id)s) of %(type)s: Wrong %(field)s in Partner',
                    name=invoice.name,
                    id=invoice.id,
                    type=(
                        _('suppliers')
                        if invoice.move_type.startswith('in_')
                        else _('customers')
                    ),
                    field=self.env['res.partner']
                    ._fields['document_type_id']
                    .string,
                )
            )
        return partner_document_type

    def _get_partner_vat(self, invoice, errors):
        try:
            partner_vat = '%.20s' % invoice.partner_id.vat.rjust(20, '0')
        except Exception as e:
            _logger.error(
                'Error on field %s: %s' % ('account_move.partner_id.vat', e)
            )
            partner_vat = False
            errors.append(
                _(
                    'Invoice %(name)s of %(type)s: Wrong %(field)s in Partner',
                    name=invoice.name,
                    type=(
                        _('suppliers')
                        if invoice.move_type.startswith('in_')
                        else _('customers')
                    ),
                    field='NIF',
                )
            )
        return partner_vat

    def _get_partner_name(self, invoice, errors):
        try:
            partner_name = '%.30s' % invoice.partner_id.get_clean_name().ljust(
                30, ' '
            )
        except Exception as e:
            _logger.error(
                'Error on field %s: %s' % ('account_move.partner_id.name', e)
            )
            partner_name = False
            errors.append(
                _(
                    'Invoice %(name)s of %(type)s: Wrong %(field)s in Partner',
                    name=invoice.name,
                    type=(
                        _('suppliers')
                        if invoice.move_type.startswith('in_')
                        else _('customers')
                    ),
                    field=self.env['res.partner']._fields['name'].string,
                )
            )
        return partner_name

    def _get_invoice_amount_total(self, invoice):
        try:
            amount_total = self._get_amount_original_currency(
                invoice, invoice.amount_total, invoice.amount_total_cur
            )
        except Exception:
            amount_total = self._get_amount_original_currency(
                invoice, invoice.amount_total, False
            )
        return amount_total

    def _get_invoice_amount_no_taxed(self, invoice):
        try:
            if invoice.is_purchase_document() and invoice.denomination in [
                'B',
                'C',
            ]:
                amount_total_no_taxed = ('%016.2f' % 0).replace('.', '')
            else:
                amount_total_no_taxed = self._get_amount_original_currency(
                    invoice,
                    invoice.amount_no_taxed,
                    invoice.amount_no_taxed_cur,
                )
        except Exception:
            amount_total_no_taxed = self._get_amount_original_currency(
                invoice, invoice.amount_no_taxed, False
            )
        return amount_total_no_taxed

    def _get_invoice_amount_exempt(self, invoice):
        try:
            amount_exempt = self._get_amount_original_currency(
                invoice, invoice.amount_exempt, invoice.amount_exempt_cur
            )
        except Exception:
            amount_exempt = self._get_amount_original_currency(
                invoice, invoice.amount_exempt, False
            )
        return amount_exempt

    def _get_invoice_currency(self, invoice, errors):
        try:
            currency_code = '%.3s' % str(invoice.currency_id.afip_code).rjust(
                3, '0'
            )
        except Exception as e:
            _logger.error(
                'Error on field %s: %s' % ('account_move.currency_id', e)
            )
            currency_code = False
            errors.append(
                _(
                    'Invoice %(name)s of %(type)s: Wrong %(field)s',
                    name=invoice.name,
                    type=(
                        _('suppliers')
                        if invoice.move_type.startswith('in_')
                        else _('customers')
                    ),
                    field=self.env['account.move']
                    ._fields['currency_id']
                    .string,
                )
            )
        return currency_code

    def _get_invoice_currency_rate(self, invoice, errors):
        try:
            if invoice.__contains__('currency_rate'):
                currency_rate = ('%011.6f' % invoice.currency_rate).replace(
                    '.', ''
                )
            else:
                currency_rate = ('%011.6f' % 1).replace('.', '')
        except Exception as e:
            _logger.error(
                'Error on field %s: %s' % ('account_move.currency_rate', e)
            )
            currency_rate = False
            errors.append(
                _(
                    'Invoice %(name)s of %(type)s: Wrong %(field)s',
                    name=invoice.name,
                    type=(
                        _('suppliers')
                        if invoice.move_type.startswith('in_')
                        else _('customers')
                    ),
                    field=self.env['account.move']
                    ._fields['currency_rate']
                    .string,
                )
            )
        return currency_rate

    def _check_invoice_is_exempt(self, invoice):
        return (
            any(
                line.tax_line_id
                and line.tax_line_id.is_exempt
                and line.tax_line_id.tax_group_id.group_type == 'vat'
                for line in invoice.line_ids
            )
            or len(self._get_invoice_tax_lines(invoice)) == 0
        )

    # METHODS TO GIVE FORMAT TO EACH LINES:
    def _format_sale_aliquot_line(self, tax_line, invoice, zero_base=False):
        errors = []
        pos = self._get_invoice_point_of_sale(invoice, errors)
        voucher_type = self._get_invoice_voucher_type(invoice, errors)
        internal_number_formatted, import_clearance = self._get_invoice_number(
            invoice, errors
        )

        if zero_base:
            line = [
                voucher_type,
                pos,
                internal_number_formatted,
                ('%016.2f' % zero_base).replace('.', ''),
                ('%.4s' % '3'.rjust(4, '0')),
                ('%016.2f' % 0).replace('.', ''),
            ]
        else:
            tax_base = tax_line.tax_base_amount
            if invoice.is_multi_currency:
                rate = invoice.currency_rate
                if invoice.currency_id.preciated:
                    rate = 1 / rate
                tax_base = tax_base * rate

            tax_amount = abs(tax_line.amount_currency)
            line = [
                voucher_type,
                pos,
                internal_number_formatted,
                ('%016.2f' % tax_base).replace('.', ''),
                ('%.4s' % str(tax_line.tax_line_id.afip_code).rjust(4, '0')),
                ('%016.2f' % tax_amount).replace('.', ''),
            ]
        if False in line:
            errors = '\n'.join(errors)
            return (False, errors)
        return (True, line)

    def _format_aliquot_purchase_line(self, tax_line, invoice, zero_base=False):
        errors = []
        pos = self._get_invoice_point_of_sale(invoice, errors)
        voucher_type = self._get_invoice_voucher_type(invoice, errors)
        partner_document_type = self._get_partner_doc_type(invoice, errors)
        partner_vat = self._get_partner_vat(invoice, errors)
        internal_number_formatted, import_clearance = self._get_invoice_number(
            invoice, errors
        )

        if zero_base:
            line = [
                voucher_type,
                pos,
                internal_number_formatted,
                partner_document_type,
                partner_vat,
                ('%016.2f' % zero_base).replace('.', ''),
                ('%.4s' % '3'.rjust(4, '0')),
                ('%016.2f' % 0).replace('.', ''),
            ]
        else:
            tax_base = tax_line.tax_base_amount
            if invoice.is_multi_currency:
                rate = invoice.currency_rate
                if invoice.currency_id.preciated:
                    rate = 1 / rate
                tax_base = tax_base * rate

            tax_amount = abs(tax_line.amount_currency)

            line = [
                voucher_type,
                pos,
                internal_number_formatted,
                partner_document_type,
                partner_vat,
                ('%016.2f' % tax_base).replace('.', ''),
                ('%.4s' % str(tax_line.tax_line_id.afip_code).rjust(4, '0')),
                ('%016.2f' % tax_amount).replace('.', ''),
            ]
        if False in line:
            errors = '\n'.join(errors)
            return (False, errors)
        return (True, line)

    def _format_aliquot_import_line(self, tax_line, invoice):
        errors = []
        internal_number_formatted, import_clearance = self._get_invoice_number(
            invoice, errors
        )

        tax_base = tax_line.tax_base_amount
        if invoice.is_multi_currency:
            rate = invoice.currency_rate
            if invoice.currency_id.preciated:
                rate = 1 / rate
            tax_base = tax_base * rate
        tax_amount = abs(tax_line.amount_currency)

        line = [
            import_clearance,
            ('%016.2f' % tax_base).replace('.', ''),
            ('%.4s' % str(tax_line.tax_line_id.afip_code).rjust(4, '0')),
            ('%016.2f' % tax_amount).replace('.', ''),
        ]
        if False in line:
            errors = '\n'.join(errors)
            return (False, errors)
        return (True, line)

    # METHODS TO CREATE MAIN LINES FOR EACH FILE
    def _create_sale_line(self, invoice):
        errors = []
        date = self._get_invoice_date(invoice, errors)
        voucher_type = self._get_invoice_voucher_type(invoice, errors)
        pos = self._get_invoice_point_of_sale(invoice, errors)
        internal_number_formatted, import_clearance = self._get_invoice_number(
            invoice, errors
        )
        partner_document_type = self._get_partner_doc_type(invoice, errors)
        partner_vat = self._get_partner_vat(invoice, errors)
        partner_name = self._get_partner_name(invoice, errors)
        amount_total = self._get_invoice_amount_total(invoice)
        amount_total_no_taxed = self._get_invoice_amount_no_taxed(invoice)
        amount_exempt = self._get_invoice_amount_exempt(invoice)
        currency_code = self._get_invoice_currency(invoice, errors)
        currency_rate = self._get_invoice_currency_rate(invoice, errors)
        tax_lines_qty = self._get_tax_lines_qty(invoice)
        operation_code = self._get_operation_code(invoice)
        has_iva_exempt = self._check_invoice_is_exempt(invoice)
        if has_iva_exempt:
            amount_total_no_taxed = ('%016.2f' % 0).replace('.', '')
            amount_exempt = ('%016.2f' % 0).replace('.', '')
            tax_lines_qty = u'{}'.format(1)
            operation_code = 'E'

        uncategorized_perception = ('%016.2f' % 0).replace(
            '.', ''
        )  # This field doesn't exist anymore, so filled with 0
        amount_national_perception = self._get_perception_with_type(
            invoice, 'nacional'
        )
        amount_iibb = self._get_perception_with_type(invoice, 'provincial')
        amount_municipal_perception = self._get_perception_with_type(
            invoice, 'municipal'
        )
        amount_internal_taxes = self._get_taxes_with_type(invoice, 'internals')
        amount_other_taxes = self._get_taxes_with_type_others(invoice)
        try:
            if (
                invoice.denomination in ['E'] and voucher_type in ['020', '021']
            ) or (
                invoice.move_type == 'out_refund'
                or (
                    invoice.move_type == 'out_invoice' and invoice.is_debit_note
                )
            ):
                date_due = '00000000'
            else:
                date_due = invoice.invoice_date_due.strftime('%Y%m%d')
        except Exception as e:
            _logger.error(
                'Error on field %s: %s' % ('account_move.invoice_date_due', e)
            )
            date_due = False
            errors.append(
                _(
                    'Invoice %(name)s of %(type)s: Wrong %(field)s',
                    name=invoice.name,
                    type=(
                        _('suppliers')
                        if invoice.move_type.startswith('in_')
                        else _('customers')
                    ),
                    field=self.env['account.move']
                    ._fields['invoice_date_due']
                    .string,
                )
            )

        line = [
            date,
            voucher_type,
            pos,
            internal_number_formatted,
            internal_number_formatted,
            partner_document_type,
            partner_vat,
            partner_name,
            amount_total,
            amount_total_no_taxed,
            uncategorized_perception,
            amount_exempt,
            amount_national_perception,
            amount_iibb,
            amount_municipal_perception,
            amount_internal_taxes,
            currency_code,
            currency_rate,
            tax_lines_qty,
            operation_code,
            amount_other_taxes,
            date_due,
        ]
        if False in line:
            errors = '\n'.join(errors)
            return (False, errors)
        return (True, line)

    def _create_sale_aliq_line(self, invoice, split_vals=False):
        aliquot_lines = []
        errors = []
        if invoice.denomination in ['C']:
            return (True, aliquot_lines)
        zero_vat_values = invoice.get_amounts_by_vat_aliquot(0, 'invoice')
        if zero_vat_values and zero_vat_values.get('base', 0):
            line = self._format_sale_aliquot_line(
                None, invoice, zero_base=zero_vat_values['base']
            )
            if line[0]:
                aliquot_line = ''.join(line[1]) if not split_vals else line[1]
                aliquot_lines.append(aliquot_line)
            else:
                errors.append(line[1])
        for tax_line in self._get_invoice_vat_tax_lines(invoice):
            line = self._format_sale_aliquot_line(tax_line, invoice)
            if line[0]:
                aliquot_line = ''.join(line[1]) if not split_vals else line[1]
                aliquot_lines.append(aliquot_line)
            else:
                errors.append(line[1])
        if len(errors) > 0:
            return (False, errors)
        return (True, aliquot_lines)

    def _create_purchase_line(self, invoice):
        errors = []

        date = self._get_invoice_date(invoice, errors)
        voucher_type = self._get_invoice_voucher_type(invoice, errors)
        pos = self._get_invoice_point_of_sale(invoice, errors)
        internal_number_formatted, import_clearance = self._get_invoice_number(
            invoice, errors
        )
        partner_document_type = self._get_partner_doc_type(invoice, errors)
        partner_vat = self._get_partner_vat(invoice, errors)
        partner_name = self._get_partner_name(invoice, errors)
        amount_total = self._get_invoice_amount_total(invoice)
        amount_total_no_taxed = self._get_invoice_amount_no_taxed(invoice)
        amount_exempt = self._get_invoice_amount_exempt(invoice)
        currency_code = self._get_invoice_currency(invoice, errors)
        currency_rate = self._get_invoice_currency_rate(invoice, errors)
        tax_lines_qty = self._get_tax_lines_qty(invoice)
        operation_code = self._get_operation_code(invoice)
        has_iva_exempt = self._check_invoice_is_exempt(invoice)
        if has_iva_exempt:
            operation_code = 'E'
        amount_iva = self._get_perception_with_type(invoice, 'vat')
        fiscal_credit = self._get_fiscal_credit_currency(invoice)
        fiscal_credit = ('%016.2f' % fiscal_credit).replace('.', '')
        amount_ganancias = self._get_perception_with_type(invoice, 'profit')
        amount_iibb = self._get_perception_with_type(invoice, 'provincial')
        amount_municipal_perception = self._get_perception_with_type(
            invoice, 'municipal'
        )
        amount_other_taxes = self._get_taxes_with_type_others(invoice)
        amount_internal_taxes = self._get_taxes_with_type(invoice, 'internals')

        # TODO: add fields and logic for this fields:
        emitter_cuit = '%.15s' % '0'.ljust(11, '0')
        emitter_denomination = '%.30s' % ' '.ljust(30, ' ')
        iva_commission = '%.15s' % '0'.ljust(15, '0')

        line = [
            date,
            voucher_type,
            pos,
            internal_number_formatted,
            import_clearance,
            partner_document_type,
            partner_vat,
            partner_name,
            amount_total,
            amount_total_no_taxed,
            amount_exempt,
            amount_iva,
            amount_ganancias,
            amount_iibb,
            amount_municipal_perception,
            amount_internal_taxes,
            currency_code,
            currency_rate,
            tax_lines_qty,
            operation_code,
            fiscal_credit,
            amount_other_taxes,
            emitter_cuit,
            emitter_denomination,
            iva_commission,
        ]
        if False in line:
            errors = '\n'.join(errors)
            return (False, errors)

        return (True, line)

    def _create_aliquot_purchase_line(self, invoice, split_vals=False):
        aliquot_lines = []
        errors = []
        if invoice.denomination in ['C']:
            return (True, aliquot_lines)
        for tax_line in self._get_invoice_vat_tax_lines(invoice):
            line = self._format_aliquot_purchase_line(tax_line, invoice)
            if line[0]:
                aliquot_line = ''.join(line[1]) if not split_vals else line[1]
                aliquot_lines.append(aliquot_line)
            else:
                errors.append(line[1])
        zero_vat_values = invoice.get_amounts_by_vat_aliquot(0, 'invoice')
        if zero_vat_values and zero_vat_values.get('base', 0):
            line = self._format_aliquot_purchase_line(
                None, invoice, zero_base=zero_vat_values['base']
            )
            if line[0]:
                aliquot_line = ''.join(line[1])
                aliquot_lines.append(aliquot_line)
            else:
                errors.append(line[1])
        if len(errors) > 0:
            return (False, errors)
        return (True, aliquot_lines)

    def _create_aliquot_import_purchase_line(self, invoice):
        aliquot_lines = []
        errors = []

        for tax_line in self._get_invoice_vat_tax_lines(invoice):
            line = self._format_aliquot_import_line(tax_line, invoice)
            if line[0]:
                aliquot_line = ''.join(line[1])
                aliquot_lines.append(aliquot_line)
            else:
                errors.append(line[1])
        if len(errors) > 0:
            return (False, errors)
        return (True, aliquot_lines)

    # METHOD TO CREATE FILES AND ATTACHMENTS:
    def create_attachment(self, suffix, filename, regs):
        tmp_filename = tempfile.mkstemp(suffix=suffix)[1]
        with codecs.open(tmp_filename, "w") as f:
            for r in regs:
                sanitized = r.encode('latin1', 'replace')
                sanitized = sanitized.decode('latin-1')
                f.write(sanitized)
                f.write('\r\n')

        generated_file_rec = self.env['libroiva.generated.files'].create(
            {
                'code': filename,
                'date_from': self.date_from,
                'date_to': self.date_to,
                'company_id': self.company_id.id,
            }
        )

        with open(tmp_filename) as f:
            data_attach = {
                'name': filename,
                'datas': binascii.b2a_base64(f.read().encode('latin-1')),
                'store_fname': filename,
                'res_model': 'libroiva.generated.files',
                'res_id': generated_file_rec.id,
            }
            new_attachment = self.env['ir.attachment'].create(data_attach)
            generated_file_rec.write({'attachment_id': new_attachment.id})
            f.close()

    def create_sales_voucher_file(self, invoices):
        aliquots = []
        aliquot_errors = []
        sales = []
        sale_errors = []

        for invoice in invoices:
            line = self._create_sale_line(invoice)
            if line[0]:
                aliquot_line = self._create_sale_aliq_line(invoice)
                if aliquot_line[0]:
                    aliquots += aliquot_line[1]
                else:
                    if aliquot_line[1]:
                        aliquot_errors.append(aliquot_line[1])

                sales.append(''.join(line[1]))
            else:
                if line[1]:
                    sale_errors.append(line[1])

        if aliquot_errors:
            aliquot_errors.insert(
                0, _('\nSale Aliquot File Errors\n================\n')
            )

        suffix = ".libroivadigitalsalesaliquot"
        filename = (
            "LIBRO_IVA_VENTAS_ALICUOTAS_%s.txt"
            % self.company_id.name.replace(' ', '-')
        )
        if aliquots:
            self.create_attachment(suffix, filename, aliquots)

        if sale_errors:
            sale_errors.insert(0, _('\nSale File Errors\n================\n'))

        suffix = ".libroivadigitalsales"
        filename = (
            "LIBRO_IVA_VENTAS_CBTE_%s.txt"
            % self.company_id.name.replace(' ', '-')
        )
        if sales:
            self.create_attachment(suffix, filename, sales)

        return (sale_errors, aliquot_errors)

    def create_purchases_voucher_file(self, invoices):  # noqa
        purchases = []
        purchase_aliquots = []
        imports = []
        import_aliquots = []
        purchase_errors = []
        purchase_aliquot_errors = []
        imports_errors = []
        import_aliquot_errors = []

        for invoice in invoices:
            is_import = invoice.iva_digital_operation_code in ['X', 'Z']
            add_purchase_line = True
            line = self._create_purchase_line(invoice)
            if line[0]:
                if is_import:
                    if self.is_simple_vat:
                        add_purchase_line = False
                    aliquot_import_line = (
                        self._create_aliquot_import_purchase_line(invoice)
                    )
                    if aliquot_import_line[0]:
                        import_aliquots += aliquot_import_line[1]
                    else:
                        if aliquot_import_line[1]:
                            import_aliquot_errors.append(aliquot_import_line[1])
                else:
                    aliquot_line = self._create_aliquot_purchase_line(invoice)
                    if aliquot_line[0]:
                        purchase_aliquots += aliquot_line[1]
                    else:
                        purchase_aliquot_errors.append(aliquot_line[1])
                if add_purchase_line:
                    purchases.append(''.join(line[1]))
                else:
                    imports.append(''.join(line[1]))
            elif line[1]:
                if is_import:
                    imports_errors.append(line[1])
                else:
                    purchase_errors.append(line[1])

        if imports_errors:
            imports_errors.insert(
                0, _('\nImport File Errors\n================\n')
            )

        suffix = ".libroivadigitalimport"
        filename = (
            "LIBRO_IVA_IMPORTACION_BIENES_%s.txt"
            % self.company_id.name.replace(' ', '-')
        )
        if imports:
            self.create_attachment(suffix, filename, imports)

        if import_aliquot_errors:
            import_aliquot_errors.insert(
                0, _('\nImport Aliquot File Errors\n================\n')
            )

        suffix = ".libroivadigitalimportaliquot"
        filename = (
            "LIBRO_IVA_IMPORTACION_BIENES_ALICUOTA_%s.txt"
            % self.company_id.name.replace(' ', '-')
        )
        if import_aliquots:
            self.create_attachment(suffix, filename, import_aliquots)

        if purchase_aliquot_errors:
            purchase_aliquot_errors.insert(
                0, _('\nPurchase Aliquot File Errors\n================\n')
            )

        suffix = ".libroivadigitalpurchasesaliquot"
        filename = (
            "LIBRO_IVA_COMPRAS_ALICUOTAS_%s.txt"
            % self.company_id.name.replace(' ', '-')
        )
        if purchase_aliquots:
            self.create_attachment(suffix, filename, purchase_aliquots)

        if purchase_errors:
            purchase_errors.insert(
                0, _('\nPurchase File Errors\n================\n')
            )

        suffix = ".libroivadigitalpurchases"
        filename = (
            "LIBRO_IVA_COMPRAS_CBTE_%s.txt"
            % self.company_id.name.replace(' ', '-')
        )
        if purchases:
            self.create_attachment(suffix, filename, purchases)

        return (purchase_errors, purchase_aliquot_errors, import_aliquot_errors)

    # INIT:
    def create_files(self):
        self._check_date_to()

        AccountMove = self.env['account.move']

        domain = [
            ('company_id', '=', self.company_id.id),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('state', '=', 'posted'),
        ]

        invoices = AccountMove.search(
            [('move_type', 'in', ('out_invoice', 'out_refund'))] + domain
        )

        invoice_purchase_ids = AccountMove.search(
            [('move_type', 'in', ('in_invoice', 'in_refund'))] + domain
        )

        if self.file_format == 'txt':
            sale_err, sale_aliquot_err = self.create_sales_voucher_file(
                invoices
            )

            (
                purchase_err,
                purchase_aliquot_err,
                import_aliquot_err,
            ) = self.create_purchases_voucher_file(invoice_purchase_ids)

            errors = (
                sale_err
                + sale_aliquot_err
                + purchase_err
                + purchase_aliquot_err
                + import_aliquot_err
            )

        elif self.file_format == 'xlsx':
            sale_err, sale_aliquot_err = self.create_sales_voucher_file_xlsx(
                invoices
            )

            (
                purchase_err,
                purchase_aliquot_err,
                import_aliquot_err,
            ) = self.create_purchases_voucher_file_xlsx(invoice_purchase_ids)

            errors = (
                sale_err
                + sale_aliquot_err
                + purchase_err
                + purchase_aliquot_err
                + import_aliquot_err
            )

        if errors:
            self.write({'notes': '\n'.join(errors)})

            return {
                'name': _('Libro IVA Digital Exporter'),
                'res_id': self.id,
                'res_model': 'libro.iva.exporter.wizard',
                'target': 'new',
                'type': 'ir.actions.act_window',
                'views': [
                    (
                        self.env.ref(
                            'l10n_ar_eynes.libro_iva_exporter_view'
                        ).id,
                        'form',
                    )
                ],
            }

        return {
            'name': _('Libro IVA generated files'),
            'res_model': 'libroiva.generated.files',
            'type': 'ir.actions.act_window',
            'view_mode': 'tree,form',
            'view_type': 'form',
        }

    def create_attachment_xlsx(self, filename, data):
        wb = Workbook()
        ws = wb.active

        for row in data:
            ws.append(row)

        fp = io.BytesIO()
        wb.save(fp)
        fp.seek(0)

        attachment = self.env['ir.attachment'].create(
            {
                'name': filename,
                'datas': base64.b64encode(fp.read()),
                'res_model': 'libroiva.generated.files',
                'res_id': self.id,
                'type': 'binary',
            }
        )

        self.env['libroiva.generated.files'].create(
            {
                'code': filename,
                'date_from': self.date_from,
                'date_to': self._get_date_to(),
                'company_id': self.company_id.id,
                'attachment_id': attachment.id,
            }
        )

    def create_sales_voucher_file_xlsx(self, invoices):
        aliquots = []
        aliquot_errors = []
        sales = []
        sale_errors = []

        for invoice in invoices:
            line = self._create_sale_line(invoice)
            if line[0]:
                aliquot_line = self._create_sale_aliq_line(
                    invoice, split_vals=True
                )
                if aliquot_line[0]:
                    aliquots += [
                        self.format_sale_aliquot_line_xlsx(line)
                        for line in aliquot_line[1]
                    ]
                else:
                    if aliquot_line[1]:
                        aliquot_errors.append(aliquot_line[1])
                sales.append(self.format_sale_line_xlsx(line[1]))
            else:
                if line[1]:
                    sale_errors.append(line[1])

        if aliquot_errors:
            aliquot_errors.insert(
                0, _('\nSale Aliquot File Errors\n================\n')
            )

        if aliquots:
            filename = (
                "LIBRO_IVA_VENTAS_ALICUOTAS_%s.xlsx"
                % self.company_id.name.replace(' ', '-')
            )
            data = [self.get_sale_aliquot_fields()] + aliquots
            self.create_attachment_xlsx(filename, data)

        if sale_errors:
            sale_errors.insert(0, _('\nSale File Errors\n================\n'))

        if sales:
            filename = (
                "LIBRO_IVA_VENTAS_CBTE_%s.xlsx"
                % self.company_id.name.replace(' ', '-')
            )
            data = [self.get_sale_fields()] + sales
            self.create_attachment_xlsx(filename, data)

        return (sale_errors, aliquot_errors)

    def create_purchases_voucher_file_xlsx(self, invoices):  # noqa
        import_aliquot_errors = []
        import_aliquots = []
        purchase_aliquot_errors = []
        purchase_aliquots = []
        purchase_errors = []
        purchases = []

        for invoice in invoices:
            line = self._create_purchase_line(invoice)
            if line[0]:
                aliquot_line = self._create_aliquot_purchase_line(
                    invoice, split_vals=True
                )
                if invoice.iva_digital_operation_code in ['X', 'Z']:
                    aliquot_import_line = (
                        self._create_aliquot_import_purchase_line(invoice)
                    )
                    if aliquot_import_line[0]:
                        import_aliquots += aliquot_import_line[1]
                    else:
                        if aliquot_import_line[1]:
                            import_aliquot_errors.append(aliquot_import_line[1])
                if aliquot_line and aliquot_line[0]:
                    purchase_aliquots += [
                        self.format_purchase_aliquot_line_xlsx(line)
                        for line in aliquot_line[1]
                    ]
                elif aliquot_line and not aliquot_line[0]:
                    if aliquot_line[1]:
                        purchase_aliquot_errors.append(aliquot_line[1])
                purchases.append(self.format_purchase_line_xlsx(line[1]))
            else:
                if line[1]:
                    purchase_errors.append(line[1])

        if purchase_aliquot_errors:
            purchase_aliquot_errors.insert(
                0, _('\nPurchase Aliquot File Errors\n================\n')
            )

        if purchase_aliquots:
            filename = (
                "LIBRO_IVA_COMPRAS_ALICUOTAS_%s.xlsx"
                % self.company_id.name.replace(' ', '-')
            )
            data = [self.get_purchase_aliquot_fields()] + purchase_aliquots
            self.create_attachment_xlsx(filename, data)

        if purchase_errors:
            purchase_errors.insert(
                0, _('\nPurchase File Errors\n================\n')
            )

        if purchases:
            filename = (
                "LIBRO_IVA_COMPRAS_CBTE_%s.xlsx"
                % self.company_id.name.replace(' ', '-')
            )
            data = [self.get_purchase_fields()] + purchases
            self.create_attachment_xlsx(filename, data)

        return (purchase_errors, purchase_aliquot_errors, import_aliquot_errors)

    def get_sale_fields(self):
        return [
            'Fecha de comprobante',
            'Tipo de comprobante',
            'Punto de venta',
            'Número de comprobante',
            'Número de comprobante hasta',
            'Código de documento del comprador',
            'Número de identificación del comprador',
            'Apellido y nombre o denominación del comprador',
            'Importe total de la operación',
            'Importe total de conceptos que no integran el precio neto gravado',
            'Percepción a no categorizados',
            'Importe de operaciones exentas',
            'Importe de percepciones o pagos a cuenta de impuestos Nacionales',
            'Importe de percepciones de Ingresos Brutos',
            'Importe de percepciones impuestos Municipales',
            'Importe impuestos internos',
            'Código de moneda',
            'Tipo de cambio',
            'Cantidad de alícuotas de IVA',
            'Código de operación',
            'Otros Tributos',
            'Fecha de Vencimiento o Pago',
        ]

    def get_sale_aliquot_fields(self):
        return [
            'Tipo de comprobante',
            'Punto de venta',
            'Número de comprobante',
            'Importe neto gravado',
            'Alícuota de IVA',
            'Impuesto Liquidado',
        ]

    def get_purchase_fields(self):
        return [
            'Fecha de comprobante o fecha de oficialización',
            'Tipo de comprobante',
            'Punto de venta',
            'Número de comprobante',
            'Despacho de importación',
            'Código de documento del vendedor',
            'Número de identificación del vendedor',
            'Apellido y nombre o denominación del vendedor',
            'Importe total de la operación',
            'Importe total de conceptos que no integran el precio neto gravado',
            'Importe de operaciones exentas',
            'Importe de percepciones o pagos a cuenta del Impuesto al Valor Agregado',
            'Importe de percepciones o pagos a cuenta de otros impuestos nacionales',
            'Importe de percepciones de Ingresos Brutos',
            'Importe de percepciones de Impuestos Municipales',
            'Importe de Impuestos Internos',
            'Código de moneda',
            'Tipo de cambio',
            'Cantidad de alícuotas de IVA',
            'Código de operación',
            'Crédito Fiscal Computable',
            'Otros Tributos',
            'CUIT emisor/corredor',
            'Denominación del emisor/corredor',
            'IVA comisión',
        ]

    def get_purchase_aliquot_fields(self):
        return [
            'Tipo de comprobante',
            'Punto de venta',
            'Número de comprobante',
            'Código de documento del vendedor',
            'Número de identificación del vendedor',
            'Importe neto gravado',
            'Alícuota de IVA',
            'Impuesto liquidado',
        ]

    def format_sale_line_xlsx(self, line):
        # 13 enteros 2 decimales
        amount_indexes = [
            8,  # Importe total de la operación
            9,  # Importe total de conceptos que no integran el precio neto gravado
            10,  # Percepción a no categorizados
            11,  # Importe de operaciones exentas
            12,  # Importe de percepciones o pagos a cuenta de impuestos Nacionales
            13,  # Importe de percepciones de Ingresos Brutos
            14,  # Importe de percepciones impuestos Municipales
            15,  # Importe impuestos internos
            20,  # Otros Tributos
        ]
        for index in amount_indexes:
            line[index] = line[index][:13] + ',' + line[index][13:]
        # 4 enteros 6 decimales
        amount_indexes = [
            17,  # Tipo de cambio
        ]
        for index in amount_indexes:
            line[index] = line[index][:4] + ',' + line[index][4:]
        return line

    def format_sale_aliquot_line_xlsx(self, line):
        # 13 enteros 2 decimales
        amount_indexes = [
            3,  # Importe neto gravado
            5,  # Impuesto Liquidado
        ]
        for index in amount_indexes:
            line[index] = line[index][:13] + ',' + line[index][13:]
        return line

    def format_purchase_line_xlsx(self, line):
        # 13 enteros 2 decimales
        amount_indexes = [
            8,  # Importe total de la operación
            9,  # mporte total de conceptos que no integran el precio neto gravado
            10,  # Importe de operaciones exentas
            11,  # Importe de percepciones o pagos a cuenta del Impuesto al Valor Agregado
            12,  # Importe de percepciones o pagos a cuenta de otros impuestos nacionales
            13,  # Importe de percepciones de Ingresos Brutos
            14,  # Importe de percepciones de Impuestos Municipales
            15,  # Importe de Impuestos Internos
            20,  # Crédito Fiscal Computable
            21,  # Otros Tributos
            24,  # IVA comisión
        ]
        for index in amount_indexes:
            line[index] = line[index][:13] + ',' + line[index][13:]
        # 4 enteros 6 decimales
        amount_indexes = [
            17,  # Tipo de cambio
        ]
        for index in amount_indexes:
            line[index] = line[index][:4] + ',' + line[index][4:]
        return line

    def format_purchase_aliquot_line_xlsx(self, line):
        # 13 enteros 2 decimales
        amount_indexes = [
            5,  # Importe neto gravado
            7,  # Impuesto Liquidado
        ]
        for index in amount_indexes:
            line[index] = line[index][:13] + ',' + line[index][13:]
        return line
