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
from odoo.tools import groupby

from ..utils.arba_fixed_width_dicts import HEAD_LINES_RET
from ..utils.sicore_fixed_width import FixedWidth, moneyfmt

_logger = logging.getLogger(__name__)


class ArbaRetentionExporterWizard(models.TransientModel):
    _name = 'arba.retention.exporter.wizard'
    _desc = 'ARBA Retention Exporter Wizard'

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
            'SELECT rtl.id '
            'FROM account_payment_order_retention_line rtl '
            'JOIN account_tax at ON rtl.retention_id = at.id '
            'JOIN account_payment_order apo ON apo.id = rtl.payment_order_id '
            'WHERE rtl.date BETWEEN %(date_from)s AND %(date_to)s '
            'AND at.retention_type IN %(type)s '
            'AND at.inform_arba = True '
            'AND apo.state = \'posted\' '
            'AND apo.company_id = %(company_id)s '
            'ORDER BY rtl.date'
        )
        cr = self.env.cr

        vals = {
            'date_from': self.date_from,
            'date_to': self.date_to,
            'type': ('gross_income',),
            'company_id': self.company_id.id,
        }
        cr.execute(query, vals)
        res = cr.fetchall()
        if not res:
            raise ValidationError(
                _(
                    'No retentions found for export.\nHINT: Check if the '
                    'retentions have the Inform ARBA field checked and/or if '
                    'the retentions\'s type is \'gross income\''
                ),
            )

        retention_ids = [r[0] for r in res]
        result = self._check_retention_tax_line_data(retention_ids)
        if isinstance(result, dict):
            raise ValidationError(result)

        self._generate_retention_file(retention_ids)

    @api.model
    def _check_retention_tax_line_data(self, retention_ids):
        RetentionTaxLine = self.env['account.payment.order.retention.line']

        errors = []

        lines = RetentionTaxLine.browse(retention_ids)
        for line in lines:
            err_list = []

            invoice = line.invoice_id
            partner = line.partner_id

            if not partner.vat:
                err_list.append('VAT for partner {}'.format(partner.name))

            if not invoice:
                err_list.append('Invoice')

            if err_list:
                reference = 'Line ID: {} - Partner: {}]'.format(
                    line.id, partner.name
                )
                err_list.insert(0, reference)
                errors.append(err_list)

        errors.insert(0, 'The following retention tax lines have missing data:')
        if errors:
            return errors

        return True

    @api.model
    def _get_arba_filename(self):
        activity_num = '6'  # 6 ~Alicuota gral
        company_vat = self._sanitize_vat(self.company_id.vat)
        lot_name = 'RET'
        period = self._get_period_code()
        filename = 'AR-{}-{}-{}-{}'.format(
            company_vat, period, activity_num, lot_name
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
    def _get_certificate_parts(self, certificate_no):
        sanitized = (certificate_no or '').strip()
        match = re.search(r'(\d{4,5})-(\d{1,8})$', sanitized)
        if match:
            return match.group(1), match.group(2)

        digits = ''.join(filter(str.isdigit, sanitized))
        if not digits:
            return '1', '0'
        if len(digits) > 8:
            return digits[:-8], digits[-8:]
        return '1', digits

    @api.model
    def _generate_retention_file(self, retention_ids):
        ArbaGeneratedFiles = self.env['arba.generated.files']
        IrAttachment = self.env['ir.attachment']
        RetentionTaxLine = self.env['account.payment.order.retention.line']

        retentions = RetentionTaxLine.browse(retention_ids)

        retention_data = [
            {
                'amount': r.amount,
                'base': r.base,
                'applied_aliquot': r.applied_aliquot,
                'certificate_no': r.certificate_no,
                'date': r.date,
                'partner_vat': r.partner_id.vat,
            }
            for r in retentions
        ]

        retention_data_sorted = sorted(
            retention_data, key=lambda x: x['certificate_no']
        )

        retention_data_filtered = []

        for _key, group in groupby(
            retention_data_sorted, key=lambda x: x['certificate_no']
        ):
            groups = list(group)
            amount_total = sum(item['amount'] for item in groups)
            base_total = sum(item['base'] for item in groups)

            first_group = groups[0]
            retention_data_filtered.append(
                {
                    'amount': amount_total,
                    'base': base_total,
                    'applied_aliquot': first_group['applied_aliquot'],
                    'certificate_no': first_group['certificate_no'],
                    'date': first_group['date'],
                    'partner_vat': first_group['partner_vat'],
                }
            )

        head_regs = []

        fixed_width = FixedWidth(HEAD_LINES_RET)

        for line in retention_data_filtered:
            date = str(line['date'])
            date = date.split('-')
            date = '{}/{}/{}'.format(date[2], date[1], date[0])

            vat = ''
            _vat = line['partner_vat']
            if _vat:
                vat = '{}-{}-{}'.format(_vat[:2], _vat[2:10], _vat[10])

            base = line['base']
            amount = line['amount']
            aliquot = 0.0
            if base:
                aliquot = round(abs(amount / base) * 100, 2)
            elif line['applied_aliquot']:
                aliquot = round(abs(line['applied_aliquot']), 2)

            branch_number, issue_number = self._get_certificate_parts(
                line['certificate_no']
            )

            vals = {
                'cuit': vat,
                'fecha_retencion': date,
                'numero_sucursal': branch_number,
                'numero_emision': issue_number,
                'monto_imponible': moneyfmt(
                    Decimal(str(base)), places=2, ndigits=12, dp=','
                ),
                'alicuota': moneyfmt(
                    Decimal(str(aliquot)), places=2, ndigits=4, dp=','
                ),
                'importe_retencion': moneyfmt(
                    Decimal(str(amount)), places=2, ndigits=11, dp=','
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
