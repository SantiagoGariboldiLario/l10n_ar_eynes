##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2012-2013 E-MIPS Electronica e Informatica
#               All Rights Reserved (<http://www.e-mips.com.ar>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

import binascii
import codecs
import logging
import re
import tempfile
import time
from decimal import Decimal

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from ..utils.sicore_fixed_width import FixedWidth, moneyfmt
from ..utils.sicore_fixed_width_dicts import HEAD_LINES, HEAD_LINES_PADRON

_logger = logging.getLogger(__name__)


class CreateSicoreFiles(models.TransientModel):
    _name = 'create.sicore.files'
    _description = 'Wizard Create sicore Files'

    period_start = fields.Date('Date start')
    period_end = fields.Date('Date end')
    notes = fields.Text('Notes')
    rrhh_ret_profit_code = fields.Char('RRHH Rule Code', default='H348')
    presentation_date = fields.Date(
        'Date of presentation', default=fields.Date.today()
    )

    @api.model
    def _parse_move_lines(self, move):

        tax_lines = {}
        concept_lines = {}

        result = {}
        amount_untaxed = 0.0
        amount_tax = 0.0
        amount_no_taxed = 0.0  # Conceptos no gravados
        amount_total = 0.0

        for line in move.line_id:
            if line.account_id.type == 'payable':
                amount_total = line.credit or line.debit
                continue

            # Lineas que son base de Impuestos de Percepcion
            if not line.credit and not line.debit:
                continue

            if line.tax_code_id.id:

                # Si la linea es una linea de IVA
                q = (
                    "SELECT t.id FROM account_tax t "
                    "JOIN account_tax_code tc ON t.tax_code_id=tc.id "
                    "WHERE tc.id=%s"
                )

                self.env.cr.execute(q, (line.tax_code_id.id,))

                # Obtenemos el account_tax correspondiente
                res = self.env.cr.fetchone()
                if res:
                    if res[0] in tax_lines:
                        tax_lines[res[0]].append(line)
                    else:
                        tax_lines[res[0]] = [line]

                    amount_tax += line.debit or line.credit
                    continue

                # Si la linea es una linea de concepto (producto)
                # y obtenemos el impuesto asociado
                q = (
                    "SELECT t.id FROM account_tax t "
                    "JOIN account_tax_code tc ON t.base_code_id=tc.id "
                    "WHERE tc.id=%s"
                )

                self.env.cr.execute(q, (line.tax_code_id.id,))

                # Obtenemos el account_tax correspondiente
                res = self.env.cr.fetchone()
                if res:
                    if res[0] in concept_lines:
                        concept_lines[res[0]].append(line)
                    else:
                        concept_lines[res[0]] = [line]
                    amount_untaxed += line.debit or line.credit
            else:
                amount_no_taxed += line.debit or line.credit

        # Neto sin impuestos
        result['amount_untaxed'] = amount_untaxed
        result['amount_tax'] = amount_tax
        result['amount_no_taxed'] = amount_no_taxed
        result['amount_total'] = amount_total
        result['concept_lines'] = concept_lines
        result['tax_lines'] = tax_lines
        return result

    def _validate_before_create(self):
        if not self.period_start:
            raise UserError(_("You must enter 'start' date"))
        if not self.period_end:
            raise UserError(_("You must enter 'end' date"))

    @api.model
    def _generate_retention_file(self, retention_ids):
        generated_files_model = self.env['sicore.generated.files']
        retention_tax_line_obj = self.env[
            'account.payment.order.retention.line'
        ]
        head_file_errors = []
        head_regs = []
        fixed_width = FixedWidth(HEAD_LINES)

        for tax_line in retention_tax_line_obj.browse(retention_ids):
            line_ident = 'Retention Tax Line #%s of Voucher #%s (%s)' % (
                tax_line.id,
                tax_line.voucher_id,
                tax_line.voucher_id.reference,
            )
            _logger.info(line_ident)
            date_voucher = time.strptime(
                tax_line.voucher_id.date, '%Y-%m-%d'
            )  # String(YYYY-MM-DD)->Datetime
            date_voucher = time.strftime(
                '%d/%m/%Y', date_voucher
            )  # Datetime->String: dd/mm/yyyy
            tipo_doc_retenido = str(
                tax_line.partner_id.document_type_id.afip_code
            )
            nro_doc_retenido = tax_line.partner_id.vat

            # First search in number then in reference
            m = re.search(r'.*(\d{4}-\d{8})$', tax_line.voucher_id.number or '')
            m2 = re.search(
                r'.*(\d{4}-\d{8})$', tax_line.voucher_id.reference or ''
            )
            if not m and not m2:
                err = (
                    '%s: Número de comprobante mal formado. Deberia ser XXXX-XXXXXXXX'
                    % line_ident
                )
                head_file_errors.append(err)
                continue
            else:
                if m:
                    internal_number = int(m.group(1).replace('-', ''))
                if m2:
                    internal_number = int(m2.group(1).replace('-', ''))

            date_emited = time.strptime(tax_line.date, '%Y-%m-%d')
            date_emited = time.strftime('%d/%m/%Y', date_emited)

            exclusion_date_certificate = tax_line.exclusion_date_certificate
            if exclusion_date_certificate:
                exclusion_date_certificate = time.strptime(
                    exclusion_date_certificate, '%Y-%m-%d'
                )
                exclusion_date_certificate = time.strftime(
                    '%d/%m/%Y', exclusion_date_certificate
                )
            else:
                exclusion_date_certificate = ''

            porcentaje_exclusion = tax_line.excluded_percent * 100

            # TODO: Esto ver si se trata del monto de la Orden de Pago
            # incluyendo todas las Retenciones o no
            amount_untaxed = 0.0
            for move_line in tax_line.move_line_ids:
                amount_untaxed += self._parse_move_lines(move_line.move_id)[
                    'amount_untaxed'
                ]

            amount_total = amount_untaxed  # tax_line.voucher_id.amount
            base_amount = tax_line.base  # Importe total de la factura
            ret_aplicada = tax_line.amount  # Importe retenido
            nro_cert_propio = re.sub('[-]', '', tax_line.certificate_no or '')
            reg_code = (
                tax_line.reg_code
                or tax_line.tax_app_id.reg_code
                or tax_line.concept_id.code
            )
            if not reg_code:
                reg_code = 0
                # raise UserError(
                #   """Error
                #   Reg. Code not found.
                #   HINT: Add Reg. Code in Tax Application
                #   (Accounting->Configuration->Retentions->Tax Application {0}->Reg.Code)"""
                #   .format(tax_line.tax_app_id.name)
                # )
            codigo_impuesto = tax_line.retention_id.code
            if not codigo_impuesto:
                raise UserError(
                    _(
                        """Error
                        code(afip_code) not found.
                        HINT: Add code to retention
                        (Accounting->Configuration->Taxes->Retentions->{}->AFIP Code)
                        """
                    ).format(tax_line.retention_id.name)
                )
            line = {
                'codigo_comprobante': '06',
                # 06: Orden de pago; HARD: Todas las ret. salen de una op
                'fecha_emision': date_voucher,
                'numero_comprobante': internal_number,
                'monto_comprobante': moneyfmt(
                    Decimal(amount_total), places=2, ndigits=13, dp=','
                ),
                'codigo_impuesto': codigo_impuesto,
                'codigo_regimen': reg_code,
                'codigo_operacion': 1,
                # 1: retencion; HARD: Exportamos retenciones
                'base_calculo': moneyfmt(
                    Decimal(base_amount), places=2, ndigits=11, dp=','
                ),
                'fecha_emision_retenc': date_emited,
                'codigo_condicion': '01',  # Inscripto (HARD: Segun longport)
                'sujetos_suspend': '',  # Beneficiarios en el exterior
                'importe_retencion': moneyfmt(
                    Decimal(ret_aplicada), places=2, ndigits=11, dp=','
                ),
                'porcentaje_exclusion': moneyfmt(
                    Decimal(porcentaje_exclusion), places=2, ndigits=3, dp=','
                ),
                'fecha_emision_boletin': exclusion_date_certificate,
                'tipo_documento_retenido': tipo_doc_retenido,
                'numero_documento_retenido': nro_doc_retenido,
                'numero_certificado_original': nro_cert_propio[2:],
                'denominacion_ordenante': tax_line.partner_id.name[:30],
                'acrecentamiento': '0',  # Segun longport
                'cuit_pais_retenido': '',  # TODO!
                'cuit_ordenante': '',  # TODO!
            }

            # Apendeamos el registro
            fixed_width.update(**line)
            head_regs.append(fixed_width.line)

        # Chequeamos si hubo errores
        if len(head_file_errors):
            return head_file_errors

        head_filename = tempfile.mkstemp(suffix='.sicore')[1]
        f = codecs.open(head_filename, "w", "latin-1")

        for r in head_regs:
            r2 = [a for a in r]
            try:
                f.write(''.join(r2))
            except Exception as e:
                raise e
            f.write('\r\n')

        f.close()

        f = open(head_filename, 'r')

        name = 'SICORE_RET_%s.txt' % self.period_start
        generated_file_rec = generated_files_model.create(
            {
                'code': name,
                'period_start': self.period_start,
                'period_end': self.period_end,
                'presentation_date': self.presentation_date,
            }
        )
        data = f.read()
        data_attach = {
            'name': name,
            'datas': binascii.b2a_base64(data),
            'datas_fname': name,
            'res_model': 'sicore.generated.files',
            'res_id': generated_file_rec.id,
        }
        self.env['ir.attachment'].create(data_attach)
        generated_file_rec.write({'attachment_id': data_attach.id})
        f.close()

        return []

    def create_files(self):
        self._validate_before_create()

        errors = ''
        cr = self._cr

        retention_query = (
            "SELECT r.id "
            "FROM account_payment_order_retention_line r "
            "JOIN account_journal ret ON r.retention_id = ret.id "
            "JOIN account_tax at ON ret.tax_id=at.id "
            "JOIN account_payment_order av ON av.name=r.voucher_number "
            "WHERE r.date BETWEEN %(date_from)s AND %(date_to)s "
            "AND ret.type in ('vat','profit') AND at.type_tax_use='purchase' "
            "AND av.state ~ 'posted' ORDER BY r.date"
        )

        cr.execute(
            retention_query,
            {'date_from': self.period_start, 'date_to': self.period_end},
        )
        res = cr.fetchall()
        if not len(res):
            raise UserError(
                _(
                    """Export Error
                    Applicable Retentions for export not found.
                    HINT:
                    The retention is of type vat or profit ?"""
                )
            )
        retention_ids = [retention_ids[0] for retention_ids in res]

        retention_errors = self._generate_retention_file(retention_ids)

        if retention_errors:
            errors += _('Retention File Errors\n================\n')
            errors += '\n'.join(retention_errors)

        if errors:
            self.write({'notes': errors})
            form_id = self.env.ref('l10n_ar_eynes.view_create_sicore_files').id
            res = {
                'name': _('Sicore'),
                'view_type': 'form',
                'view_mode': 'form',
                'views': [
                    (form_id, 'form'),
                ],
                'res_model': 'create.sicore.files',
                'res_id': self.id,
                'view_id': form_id,
                'type': 'ir.actions.act_window',
                'target': 'new',
            }
        else:
            res = True

        return res

    @api.model
    def get_data_of_employee(self, employee_id):
        """
        :ret: {'name':xx,'cuil':xx,'dni':xx,'street':xx,'city':xx,'zip':xx}
        """
        q = """
        SELECT he.name AS name, regexp_replace(he.cuil,'-','','g') as cuil,
        substring(cuil from '-(.*)-') AS dni, rp.street as street, rp.city as city, rp.zip
        FROM hr_employee he join res_partner rp ON rp.id = he.address_home_id
        WHERE he.id=%(employee_id)s
        """
        q_params = {'employee_id': employee_id}
        self._cr.execute(q, q_params)
        return self._cr.dictfetchone()

    @api.model
    def _generate_retention_file_rrhh(self, res):
        generated_files_model = self.env['sicore.generated.files']

        head_file_errors = []
        head_regs = []
        head_regs_padron = []
        fixed_width = FixedWidth(HEAD_LINES)
        fixed_width_padron = FixedWidth(HEAD_LINES_PADRON)
        for emp in res:
            ps_id, emp_id, total, date = emp
            base_amount = total
            emp_data = self.get_data_of_employee(emp_id)
            line_padron = {
                'cuil': emp_data['cuil'],
                'nombre': emp_data['name'],
                'direccion': emp_data['street'],
                'ciudad': emp_data['city'],
                'cod_provincia': '00',
                'cod_postal': str(emp_data['zip'] or ''),
                'tipo_doc': '86',
            }
            # Apendeamos el registro
            fixed_width_padron.update(**line_padron)
            head_regs_padron.append(fixed_width_padron.line)

            date_voucher = time.strptime(
                date, '%Y-%m-%d'
            )  # String(YYYY-MM-DD)->Datetime
            date_voucher = time.strftime(
                '%d/%m/%Y', date_voucher
            )  # Datetime->String: dd/mm/yyyy
            if total > 0:  # Refund
                base_amount = total
                ret_aplicada = 0
                cod_comp = 8
            elif total < 0:  # Retention
                base_amount = abs(total)
                ret_aplicada = abs(total)
                cod_comp = 7
            line = {
                'codigo_comprobante': cod_comp,  # 07: Payslip, 08: PS Ref
                'fecha_emision': date_voucher,
                'numero_comprobante': 0,
                'monto_comprobante': '',
                'codigo_impuesto': 787,
                # Impuesto a las Ganancias Retenciones Art. 79
                # de la Ley de Impuesto a las Ganancias
                'codigo_regimen': 160,
                # Rentas del trabajo personal bajo relación de dependencia y otros
                'codigo_operacion': 1,
                # 1: retention
                'base_calculo': moneyfmt(
                    Decimal(base_amount), places=2, ndigits=11, dp=','
                ),
                'fecha_emision_retenc': date_voucher,
                'codigo_condicion': '01',  # Inscripto
                'sujetos_suspend': '0',  # Beneficiarios en el exterior
                'importe_retencion': moneyfmt(
                    Decimal(ret_aplicada), places=2, ndigits=11, dp=','
                ),
                'porcentaje_exclusion': '0',
                'fecha_emision_boletin': '',
                'tipo_documento_retenido': '86',  # CUIL
                'numero_documento_retenido': emp_data['cuil'],
                'numero_certificado_original': '',
                'denominacion_ordenante': emp_data['name'],
                'acrecentamiento': '0',  # Segun longport
                'cuit_pais_retenido': '',
                'cuit_ordenante': '',
            }

            # Apendeamos el registro
            fixed_width.update(**line)
            head_regs.append(fixed_width.line)

        # Chequeamos si hubo errores
        if len(head_file_errors):
            return head_file_errors

        head_filename = tempfile.mkstemp(suffix='.sicore.rrhh')[1]
        f = codecs.open(head_filename, "w", "latin-1")

        for r in head_regs:
            r2 = [a for a in r]
            try:
                f.write(''.join(r2))
            except Exception as e:
                raise e
            f.write('\r\n')

        f.close()

        f = open(head_filename, 'rb')

        name = 'SICORE_RET_RRHH_%s.txt' % self.period_start
        generated_file_rec = generated_files_model.create(
            {
                'code': name,
                'period_start': self.period_start,
                'period_end': self.period_end,
                'presentation_date': self.presentation_date,
            }
        )
        data = f.read()
        data_attach = {
            'name': name,
            'datas': binascii.b2a_base64(data),
            'datas_fname': name,
            'res_model': 'sicore.generated.files',
            'res_id': generated_file_rec.id,
        }
        self.env['ir.attachment'].create(data_attach)
        generated_file_rec.write({'attachment_id': data_attach.id})
        f.close()

        # Write SICORE_RRHH_PADRON
        head_filename = tempfile.mkstemp(suffix='.sicore.rrhh.padron')[1]
        f = codecs.open(head_filename, "w", "latin-1")

        for r in head_regs_padron:
            r2 = [a for a in r]
            try:
                f.write(''.join(r2))
            except Exception as e:
                raise e
            f.write('\r\n')

        f.close()

        f = open(head_filename, 'rb')

        name = 'SICORE_RET_RRHH_P_%s.txt' % self.period_start
        generated_file_rec = generated_files_model.create(
            {
                'code': name,
                'period_start': self.period_start,
                'period_end': self.period_end,
                'presentation_date': self.presentation_date,
            }
        )
        data = f.read()
        data_attach = {
            'name': name,
            'datas': binascii.b2a_base64(data),
            'datas_fname': name,
            'res_model': 'sicore.generated.files',
            'res_id': generated_file_rec.id,
        }
        self.env['ir.attachment'].create(data_attach)
        generated_file_rec.write({'attachment_id': data_attach.id})
        f.close()

        return []

    def create_files_rrhh(self):
        self._validate_before_create()

        rrhh_code = self.rrhh_ret_profit_code
        if not rrhh_code:
            raise ValidationError(_('Invalid RRHH Code.'))
        errors = ''

        q = """
            SELECT pl.id payslip_id, pl.employee_id employee_id,
            SUM(psl.total) total FROM hr_payslip_line AS psl
            JOIN hr_payslip AS pl ON (pl.id=psl.slip_id)
            WHERE psl.code IN %(code)s AND pl.date BETWEEN
            %(date_from)s AND %(date_to)s AND psl.total!=0
            AND pl.state IN %(state)s GROUP BY pl.id, pl.employee_id, pl.date_to;
        """
        q_params = {
            'state': tuple(['done']),
            # 'code': self.rrhh_ret_profit_code,
            'code': tuple([self.rrhh_ret_profit_code, 'H349']),
            'date_from': self.period_start,
            'date_to': self.period_end,
        }
        self._cr.execute(q, q_params)
        res = self._cr.fetchall()
        if not len(res):
            raise UserError(
                _(
                    """Export Error
                    Applicable Retentions for export based on rule %s not found.
                    HINT: The payslips are in state done?"""
                )
                % self.rrhh_ret_profit_code
            )

        for r in range(len(res)):
            aux_tuple = (self.presentation_date,)
            res[r] = res[r] + aux_tuple

        retention_errors = self._generate_retention_file_rrhh(res)

        if retention_errors:
            errors += _('Retention File Errors\n================\n')
            errors += '\n'.join(retention_errors)

        if errors:
            self.write({'notes': errors})
            form_id = self.env.ref('l10n_ar_eynes.view_create_sicore_files').id
            res = {
                'name': _('Sicore'),
                'view_type': 'form',
                'view_mode': 'form',
                'views': [
                    (form_id, 'form'),
                ],
                'res_model': 'create.sicore.files',
                'res_id': self.id,
                'view_id': form_id,
                'type': 'ir.actions.act_window',
                'target': 'new',
            }
        else:
            res = True

        return res
