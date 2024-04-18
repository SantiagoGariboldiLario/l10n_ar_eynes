##############################################################################
#
#   Copyright (c) 2022-2023 Eynes SRL  (Eynes - Ingenieria del software)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
#
##############################################################################

import binascii
import codecs
import logging
import tempfile
from decimal import Decimal

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..utils.arba_fixed_width_dicts import HEAD_LINES_PER
from ..utils.sicore_fixed_width import FixedWidth, moneyfmt

_logger = logging.getLogger(__name__)


class ArbaPerceptionExporterWizard(models.TransientModel):
    _name = 'arba.perception.exporter.wizard'
    _desc = 'ARBA Perception Exporter Wizard'

    date_from = fields.Date(string='Date From')
    date_to = fields.Date(string='Date To')

    def create_file(self):
        query = (
            'SELECT ptl.id '
            'FROM perception_tax_line ptl '
            'JOIN account_move ai ON ptl.invoice_id = ai.id '
            'JOIN account_journal pp ON ptl.perception_id = pp.id '
            'JOIN account_tax at ON pp.tax_id = at.id '
            'WHERE ptl.date BETWEEN %(date_from)s AND %(date_to)s '
            'AND ai.state IN %(state)s '
            'AND at.inform_arba = True '
            'AND at.retention_type IN %(type)s '
            'ORDER BY ptl.date '
        )
        cr = self.env.cr

        vals = {
            'date_from': self.date_from,
            'date_to': self.date_to,
            'state': ('posted', 'paid'),
            'type': ('gross_income',),
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
                    'Voucher type for invoice {}'.format(invoice.number)
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
        activity_num = '7'  # 7 Alícuota general
        company_vat = self.env.user.company_id.vat
        lot_name = 'PER'

        month = str(self.date_from.month).zfill(2)
        year = str(self.date_from.year)

        filename = 'AR-{}-{}{}-{}-{}'.format(
            company_vat, year, month, activity_num, lot_name
        )

        return filename

    @api.model
    def _get_voucher_type(self, invoice_id):
        res = None

        if invoice_id.move_type == 'out_invoice':
            if invoice_id.is_debit_note:
                res = 'D'
            else:
                res = 'F'
        elif invoice_id.move_type == 'out_refund':
            res = 'C'

        if invoice_id.fiscal_type == 'electronic':
            electronic_invoice = {'C': 'H', 'D': 'I', 'F': 'E'}
            res = electronic_invoice.get(res)

        return res

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
            internal_number_split = line.invoice_id.internal_number.split('-')
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

            line = {
                'cuit': f_cuit,
                'fecha_percepcion': date,
                'tipo_comprobante': voucher_type,
                'letra_comprobante': line.invoice_id.denomination,
                'numero_sucursal': internal_number_split[0],
                'numero_emision': internal_number_split[1],
                # 'monto_imponible': moneyfmt(
                #     Decimal(base) * sign, places=2, ndigits=10, dp=','
                # ),
                'importe_percepcion': moneyfmt(
                    Decimal(amount) * sign, places=2, ndigits=9, dp=','
                ),
                'tipo_operacion': 'A',
            }

            fixed_width.update(**line)
            head_regs.append(fixed_width.line)

        head_filename = tempfile.mkstemp(suffix='.arba')[1]
        file = codecs.open(head_filename, 'w', 'latin-1')

        for r in head_regs:
            r2 = [a for a in r]
            try:
                file.write(''.join(r2))
            except Exception as e:
                raise e
            file.write('\r\n')

        file.close()

        file = open(head_filename, 'r', encoding='utf-8')

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
