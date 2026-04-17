##############################################################################
#
#   Copyright (c) 2022-2023 Eynes SRL  (Eynes - Ingenieria del software)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
#
##############################################################################

import base64
import calendar
import hashlib
import io
import json
import logging
import re
import zipfile
from decimal import Decimal

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..utils.arba_fixed_width_dicts import HEAD_LINES_PER
from ..utils.sicore_fixed_width import FixedWidth, moneyfmt

_logger = logging.getLogger(__name__)


class ArbaPerceptionExporterWizard(models.TransientModel):
    _name = 'arba.perception.exporter.wizard'
    _desc = 'ARBA Perception Exporter Wizard'

    company_id = fields.Many2one('res.company', 'Company', required=True)
    company_id_domain = fields.Char(
        default=lambda self: self._default_company_ids()
    )
    date_from = fields.Date(string='Date From')
    date_to = fields.Date(string='Date To')
    mode = fields.Selection(
        [
            ('monthly', 'Monthly'),
            ('first_fortnight', 'First Fortnight'),
            ('second_fortnight', 'Second Fortnight'),
        ],
        string='Mode',
        default='monthly',
        required=True,
    )

    @api.model
    def _default_company_ids(self):
        return json.dumps(
            [('id', 'in', self.env.context.get('allowed_company_ids', []))]
        )

    def create_file(self):
        query = (
            'SELECT ptl.id '
            'FROM perception_tax_line ptl '
            'JOIN account_move ai ON ptl.invoice_id = ai.id '
            'JOIN account_tax at ON ptl.perception_id = at.id '
            'WHERE ptl.date BETWEEN %(date_from)s AND %(date_to)s '
            'AND ai.state IN %(state)s '
            'AND at.inform_arba = True '
            'AND at.retention_type IN %(type)s '
            'AND ai.company_id = %(company_id)s '
            'ORDER BY ptl.date '
        )
        cr = self.env.cr

        vals = {
            'date_from': self.date_from,
            'date_to': self.date_to,
            'state': ('posted', 'paid'),
            'type': ('gross_income',),
            'company_id': self.company_id.id,
        }

        cr.execute(query, vals)
        res = cr.fetchall()
        if not res:
            raise ValidationError(
                _(
                    'No perceptions found for export.\nHINT: Check if the '
                    'perceptions have the Inform ARBA field checked and/or if '
                    'the perceptions\'s type is \'gross income\''
                ),
            )

        perception_ids = [p[0] for p in res]
        result = self._check_perception_tax_line_data(perception_ids)
        if isinstance(result, dict):
            raise ValidationError(result)

        self._generate_perception_file(perception_ids)

    @api.model
    def _check_perception_tax_line_data(self, perception_ids):
        PerceptionTaxLine = self.env['perception.tax.line']

        errors = []

        lines = PerceptionTaxLine.browse(perception_ids)
        for line in lines:
            err_list = []

            invoice = line.invoice_id
            partner = line.partner_id

            if not partner.vat:
                err_list.append('VAT for partner {}'.format(partner.name))

            if not invoice:
                err_list.append('Invoice')

            voucher_type = self._get_voucher_type(invoice)
            if not voucher_type:
                err_list.append(
                    'Voucher type for invoice {}'.format(invoice.name)
                )

            if err_list:
                reference = 'Line ID: {} - Partner: {}]'.format(
                    line.id, partner.name
                )
                err_list.insert(0, reference)
                errors.append(err_list)

        errors.insert(
            0, 'The following perception tax lines have missing data:'
        )
        if errors:
            return errors

        return True

    @api.model
    def _get_arba_filename(self):
        activity_code = 'P7'
        company_vat = self._sanitize_vat(self.company_id.vat)
        lot_name = 'PER'
        period = self._get_period_code()
        filename = 'AR-{}-{}-{}-{}'.format(
            company_vat, period, activity_code, lot_name
        )
        if self.mode == 'first_fortnight':
            filename += '-LOTE1'
        elif self.mode == 'second_fortnight':
            filename += '-LOTE2'
        return filename

    @api.model
    def _sanitize_vat(self, vat):
        return ''.join(filter(str.isdigit, vat or ''))

    @api.model
    def _get_period_code(self):
        if not self.date_from or not self.date_to:
            raise ValidationError(
                _('Both date from and date to are required for ARBA export.')
            )
        if (
            self.date_from.year != self.date_to.year
            or self.date_from.month != self.date_to.month
        ):
            raise ValidationError(
                _(
                    'ARBA export requires a single monthly or fortnightly period.'
                )
            )

        last_day = calendar.monthrange(
            self.date_from.year, self.date_from.month
        )[1]
        if self.mode == 'first_fortnight':
            expected_from, expected_to, fortnight = 1, 15, '1'
        elif self.mode == 'second_fortnight':
            expected_from, expected_to, fortnight = 16, last_day, '2'
        else:
            expected_from, expected_to, fortnight = 1, last_day, '0'

        if (
            self.date_from.day != expected_from
            or self.date_to.day != expected_to
        ):
            raise ValidationError(
                _(
                    'Selected mode does not match the date range for ARBA export.'
                )
            )

        return '{}{:02d}{}'.format(
            self.date_from.year, self.date_from.month, fortnight
        )

    @api.model
    def _build_attachment_payload(self, txt_filename, txt_content):
        txt_bytes = txt_content.encode('latin-1')
        md5_hash = hashlib.md5(txt_bytes).hexdigest().upper()
        zip_basename = '{}_{}'.format(txt_filename[:-4], md5_hash)
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(
            zip_buffer, mode='w', compression=zipfile.ZIP_DEFLATED
        ) as zip_file:
            zip_file.writestr(txt_filename, txt_bytes)
        return zip_basename + '.zip', zip_buffer.getvalue()

    @api.model
    def _get_voucher_type(self, invoice_id):
        """
        ARBA TABLE:
        'F': Factura,
        'R': Recibo,
        'C': Nota de crédito
        'D': Nota de débito
        """
        if not invoice_id:
            return False
        inv_name = invoice_id.name or ''
        if 'FCE' in inv_name:
            return 'E'
        if 'NCE' in inv_name:
            return 'H'
        if 'NDE' in inv_name:
            return 'I'
        if invoice_id.move_type == 'out_receipt':
            return 'R'
        if invoice_id.move_type == 'out_refund':
            return 'C'
        if invoice_id.is_debit_note:
            return 'D'
        return 'F'

    @api.model
    def _generate_perception_file(self, perception_ids):
        ArbaGeneratedFiles = self.env['arba.generated.files']
        IrAttachment = self.env['ir.attachment']
        PerceptionTaxLine = self.env['perception.tax.line']

        head_regs = []

        fixed_width = FixedWidth(HEAD_LINES_PER)

        lines = PerceptionTaxLine.browse(perception_ids)
        for line in lines:
            date = str(line.date)
            date = date.split('-')
            date = '{}/{}/{}'.format(date[2], date[1], date[0])

            voucher_type = self._get_voucher_type(line.invoice_id)
            if voucher_type == 'C':
                sign = -1
            else:
                sign = 1

            pattern = re.compile(r'(FCE|NCE|NDE)')
            inv_name = line.invoice_id.name
            match = pattern.search(inv_name)
            if match:
                inv_name = inv_name.replace(match.group(), '')
            pos, number = inv_name.split('-')
            pos = ''.join(filter(str.isdigit, pos))
            number = ''.join(filter(str.isdigit, number))

            if line.partner_id.document_type_id not in [
                self.env.ref('l10n_ar_eynes.document_cuit'),
                self.env.ref('l10n_ar_eynes.document_cuil'),
            ]:
                raise ValidationError(
                    _(
                        '%(partner)s has no CUIT/CUIL, it might have another kind of document.'
                        'Please, set a valid CUIT or CUIL',
                        partner=line.partner_id.name,
                    )
                )
            cuit = line.partner_id.vat
            if cuit:
                f_cuit = '{}-{}-{}'.format(cuit[:2], cuit[2:10], cuit[10])
            else:
                f_cuit = ''

            invoice = line.invoice_id
            base = line.base
            amount = line.amount
            if invoice.currency_id != invoice.company_id.currency_id:
                invoice_rate = invoice.currency_rate or 1
                base *= invoice_rate
                amount *= invoice_rate

            aliquot = 0.0
            if base:
                aliquot = round(abs(amount / base) * 100, 2)
            elif line.percent:
                aliquot = round(abs(line.percent), 2)

            vals = {
                'cuit': f_cuit,
                'fecha_percepcion': date,
                'tipo_comprobante': voucher_type,
                'letra_comprobante': (
                    line.invoice_id.denomination or ' '
                ).upper(),
                'numero_sucursal': pos,
                'numero_emision': number,
                'monto_imponible': moneyfmt(
                    Decimal(str(base)) * sign, places=2, ndigits=12, dp=','
                ),
                'alicuota': moneyfmt(
                    Decimal(str(aliquot)), places=2, ndigits=4, dp=','
                ),
                'importe_percepcion': moneyfmt(
                    Decimal(str(amount)) * sign, places=2, ndigits=11, dp=','
                ),
                'tipo_operacion': 'A',
            }

            fixed_width.update(**vals)
            head_regs.append(fixed_width.line)
        txt_name = self._get_arba_filename() + '.TXT'
        txt_content = ''.join(''.join(reg) + '\r\n' for reg in head_regs)
        name, payload = self._build_attachment_payload(txt_name, txt_content)
        generated_file_rec = ArbaGeneratedFiles.create(
            {
                'code': name,
                'date_from': self.date_from,
                'date_to': self.date_to,
                'company_id': self.company_id.id,
            }
        )

        data_attach = {
            'name': name,
            'datas': base64.b64encode(payload),
            'res_model': 'arba.generated.files',
            'res_id': generated_file_rec.id,
        }

        attach_id = IrAttachment.create(data_attach)
        generated_file_rec.write({'attachment_id': attach_id.id})

        return True
