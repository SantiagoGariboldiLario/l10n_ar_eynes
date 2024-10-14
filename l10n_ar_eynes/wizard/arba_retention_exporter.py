##############################################################################
#
#   Copyright (c) 2022-2023 Eynes SRL  (Eynes - Ingenieria del software)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
#
##############################################################################

import binascii
import codecs
import itertools
import logging

# import re
import tempfile
from decimal import Decimal

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..utils.arba_fixed_width_dicts import HEAD_LINES_RET
from ..utils.sicore_fixed_width import FixedWidth, moneyfmt

_logger = logging.getLogger(__name__)


class ArbaRetentionExporterWizard(models.TransientModel):
    _name = 'arba.retention.exporter.wizard'
    _desc = 'ARBA Retention Exporter Wizard'

    date_from = fields.Date(string='Date From')
    date_to = fields.Date(string='Date To')

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
            'ORDER BY rtl.date'
        )
        cr = self.env.cr

        vals = {
            'date_from': self.date_from,
            'date_to': self.date_to,
            'type': ('gross_income',),
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
        company_vat = self.env.user.company_id.vat
        lot_name = 'RET'

        month = str(self.date_from.month).zfill(2)
        year = str(self.date_from.year)

        filename = 'AR-{}-{}{}-{}-{}'.format(
            company_vat, year, month, activity_num, lot_name
        )

        return filename

    @api.model
    def _generate_retention_file(self, retention_ids):
        ArbaGeneratedFiles = self.env['arba.generated.files']
        IrAttachment = self.env['ir.attachment']
        RetentionTaxLine = self.env['account.payment.order.retention.line']

        retentions = RetentionTaxLine.browse(retention_ids)

        retention_data = [
            {
                'amount': r.amount,
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

        for _key, group in itertools.groupby(
            retention_data_sorted, lambda x: x['certificate_no']
        ):
            groups = list(group)
            amount_total = sum(item['amount'] for item in groups)

            first_group = groups[0]
            retention_data_filtered.append(
                {
                    'amount': amount_total,
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

            # certificate_no = '0000-00000000'
            # certificate = re.search(r'\d{4}-\d{8}$', line['certificate_no'])
            # if certificate:
            #     certificate_no = certificate.group(0)
            # certificate_no_split = certificate_no.split('-')

            line = {
                'cuit': vat,
                'fecha_retencion': date,
                'importe_retencion': moneyfmt(
                    Decimal(line['amount']), places=2, ndigits=8, dp=','
                ),
                # 'numero_sucursal': certificate_no_split[0],
                # 'numero_emision': certificate_no_split[1],
                'numero_sucursal': '1',
                'numero_emision': line['certificate_no'],
                'tipo_operacion': 'A',
            }
            fixed_width.update(**line)
            head_regs.append(fixed_width.line)

        head_filename = tempfile.mkstemp(suffix='.arba')[1]
        tmp_file = codecs.open(head_filename, 'w', 'latin-1')

        for head in head_regs:
            r2 = [a for a in head]
            try:
                tmp_file.write(''.join(r2))
            except Exception as e:
                raise e
            tmp_file.write('\r\n')

        tmp_file.close()

        file = open(head_filename, 'r')

        name = self._get_arba_filename()
        name += '.TXT'
        generated_file_rec = ArbaGeneratedFiles.create(
            {
                'code': name,
                'date_from': self.date_from,
                'date_to': self.date_to,
            }
        )

        data_attach = {
            'name': name,
            'datas': binascii.b2a_base64(file.read().encode('latin-1')),
            # 'datas_fname': name,
            'res_model': 'arba.generated.files',
            'res_id': generated_file_rec.id,
        }

        attach_id = IrAttachment.create(data_attach)
        generated_file_rec.write({'attachment_id': attach_id.id})

        file.close()
