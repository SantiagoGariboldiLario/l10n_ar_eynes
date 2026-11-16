##############################################################################
#
#   Copyright (c) 2022-2023 Eynes SRL  (Eynes - Ingenieria del software)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
#
##############################################################################

import base64
import calendar
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
    activity_code = fields.Char(
        string='Activity Code', required=True, default='6'
    )
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
        self._validate_export_configuration()
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
        if result is not True:
            raise ValidationError(result)

        self._generate_retention_file(retention_ids)

    def _validate_export_configuration(self):
        # [T15698] En v19 se conserva el bloqueo introducido con A122R: si la
        # compania informa por servicio, no se habilita ademas el TXT para
        # evitar una doble presentacion. La v17 lo habia quitado en [T14612].
        if self.company_id.arba_a122r_enforced:
            raise ValidationError(
                _(
                    'ARBA TXT export is disabled because ARBA A122R enforcement '
                    'is enabled for this company.'
                )
            )
        company_vat = self._sanitize_vat(self.company_id.vat)
        if len(company_vat) != 11:
            raise ValidationError(
                _('Company VAT must have 11 digits for ARBA export.')
            )
        activity_code = ''.join(filter(str.isdigit, self.activity_code or ''))
        if not activity_code:
            raise ValidationError(
                _('Activity Code must contain only digits for ARBA export.')
            )

    @api.model
    def _check_retention_tax_line_data(self, retention_ids):
        RetentionTaxLine = self.env['account.payment.order.retention.line']

        errors = []

        lines = RetentionTaxLine.browse(retention_ids)
        for line in lines:
            err_list = []

            # invoice_id is not used by the A-122R export layout, so we keep
            # this validation disabled to avoid blocking valid retention lines.
            # invoice = line.invoice_id
            partner = line.partner_id
            vat = self._sanitize_vat(partner.vat)
            transaction_number = self._get_transaction_number(
                line.certificate_no
            )
            branch_number, _issue_number = self._get_certificate_parts(
                line.certificate_no
            )

            if not vat:
                err_list.append('VAT for partner {}'.format(partner.name))
            elif len(vat) != 11:
                err_list.append(
                    'VAT for partner {} must have 11 digits'.format(
                        partner.name
                    )
                )

            # if not invoice:
            #     err_list.append('Invoice')

            if not branch_number or int(branch_number or 0) <= 0:
                err_list.append(
                    'Certificate branch number must be greater than zero'
                )

            if not transaction_number or len(transaction_number) != 20:
                err_list.append(
                    'Certificate No. must provide a valid 20-digit transaction number'
                )

            if err_list:
                reference = 'Line ID: {} - Partner: {}]'.format(
                    line.id, partner.name
                )
                err_list.insert(0, reference)
                errors.append(err_list)

        if errors:
            errors.insert(
                0, 'The following retention tax lines have missing data:'
            )
            return errors

        return True

    @api.model
    def _get_arba_filename(self):
        company_vat = self._sanitize_vat(self.company_id.vat)
        period = self._get_period_code()
        activity_code = ''.join(filter(str.isdigit, self.activity_code or ''))
        filename = 'ER-{}-{}-{}'.format(company_vat, period, activity_code)
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
        if self.mode == 'monthly':
            if self.date_from.day != 1 or self.date_to.day != last_day:
                raise ValidationError(
                    _('Monthly mode requires a full month period.')
                )
            fortnight = '0'
        elif self.mode == 'first_fortnight':
            if self.date_from.day != 1 or self.date_to.day > 15:
                raise ValidationError(
                    _(
                        'First fortnight mode requires a period from day 1 to day 15.'
                    )
                )
            fortnight = '1'
        else:
            if self.date_from.day < 16 or self.date_to.day != last_day:
                raise ValidationError(
                    _(
                        'Second fortnight mode requires a period from day 16 to the end of the month.'
                    )
                )
            fortnight = '2'

        return '{}{:02d}{}'.format(
            self.date_from.year, self.date_from.month, fortnight
        )

    @api.model
    def _build_attachment_payload(self, txt_filename, txt_content):
        txt_bytes = txt_content.encode('latin-1')
        zip_basename = txt_filename[:-4]
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
    def _get_transaction_number(self, certificate_no):
        digits = ''.join(filter(str.isdigit, (certificate_no or '').strip()))
        if not digits:
            return ''
        if len(digits) > 20:
            return ''
        return digits[-20:].zfill(20)

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

            vat = self._sanitize_vat(line['partner_vat'])

            base = line['base']
            amount = line['amount']
            aliquot = 0.0
            if base:
                aliquot = round(abs(amount / base) * 100, 2)
            elif line['applied_aliquot']:
                aliquot = round(abs(line['applied_aliquot']), 2)

            branch_number, _issue_number = self._get_certificate_parts(
                line['certificate_no']
            )
            transaction_number = self._get_transaction_number(
                line['certificate_no']
            )

            vals = {
                'numero_transaccion': transaction_number,
                'cuit': vat,
                'fecha_retencion': date,
                'numero_sucursal': branch_number,
                'monto_imponible': moneyfmt(
                    Decimal(str(abs(base))), places=2, ndigits=13, dp='.'
                ),
                'alicuota': moneyfmt(
                    Decimal(str(aliquot)), places=2, ndigits=2, dp='.'
                ),
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
