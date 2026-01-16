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
import json
import logging
import re
import tempfile
import time
from decimal import Decimal

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from ..utils.sicore_fixed_width import FixedWidth, moneyfmt
from ..utils.sicore_fixed_width_dicts import (
    HEAD_LINES,
    HEAD_LINES_EXTERIOR,
    HEAD_LINES_PADRON,
)

_logger = logging.getLogger(__name__)


class CreateSicoreFiles(models.TransientModel):
    _name = 'create.sicore.files'
    _description = 'Wizard Create sicore Files'

    company_id = fields.Many2one('res.company', required=True, default=False)
    company_id_domain = fields.Char(
        default=lambda self: self._default_company_ids()
    )
    notes = fields.Text('Notes')
    period_start = fields.Date('Date start')
    period_end = fields.Date('Date end')
    presentation_date = fields.Date(
        'Date of presentation', default=fields.Date.today()
    )
    rrhh_ret_profit_code = fields.Char('RRHH Rule Code', default='H348')

    @api.model
    def _default_company_ids(self):
        return json.dumps(
            [('id', 'in', self.env.context.get('allowed_company_ids', []))]
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

    def _format_monetary(self, value):
        return "{:,.2f}".format(value).replace(",", "").replace(".", ",")

    @api.model
    def _generate_retention_file(self, retention_ids, exterior=False):
        head_file_errors = []
        head_regs = []
        fixed_width = (
            FixedWidth(HEAD_LINES)
            if not exterior
            else FixedWidth(HEAD_LINES_EXTERIOR)
        )
        is_local = not exterior

        tax_lines = self.env['account.payment.order.retention.line'].browse(
            retention_ids
        )

        # Filtrar lineas según si es local o no, para sacar los archivos separados.
        if is_local:
            filtered_tax_lines = tax_lines.filtered(
                lambda line: line.partner_id.property_account_position_id.local
            )
        else:
            filtered_tax_lines = tax_lines.filtered(
                lambda line: not line.partner_id.property_account_position_id.local
            )

        for tax_line in filtered_tax_lines:
            line_ident = 'Retention Tax Line #%s of Voucher #%s (%s)' % (
                tax_line.id,
                tax_line.payment_order_id,
                tax_line.payment_order_id.reference,
            )
            _logger.info(line_ident)
            date_voucher = tax_line.payment_order_id.date.strftime(
                '%d/%m/%Y'
            )  # Datetime->String: dd/mm/yyyy
            tipo_doc_retenido = str(
                tax_line.partner_id.document_type_id.afip_code
            )
            nro_doc_retenido = tax_line.partner_id.vat

            # First search in number then in reference
            internal_number = tax_line.payment_order_id.number or ''
            if not internal_number:
                err = '%s: Número de comprobante no encontrado.' % line_ident
                head_file_errors.append(err)
                continue
            else:
                internal_number = int(re.sub(r"\D", "", internal_number))

            date_emited = tax_line.date.strftime('%d/%m/%Y')

            exclusion_date_certificate = tax_line.exclusion_date_certificate
            if exclusion_date_certificate:
                exclusion_date_certificate = (
                    exclusion_date_certificate.strftime('%d/%m/%Y')
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
            base_amount = tax_line.base_amount
            ret_aplicada = tax_line.amount  # Importe retenido
            nro_cert_propio = re.sub('[-]', '', tax_line.certificate_no or '')
            reg_code = (
                tax_line.reg_code
                or tax_line.taxapp_id.reg_code
                or tax_line.concept_id.code
            )
            reg_code = str(reg_code)[:3] if reg_code else False
            if not reg_code:
                reg_code = 0
                # raise UserError(
                #   """Error
                #   Reg. Code not found.
                #   HINT: Add Reg. Code in Tax Application
                #   (Accounting->Configuration->Retentions->Tax Application {0}->Reg.Code)"""
                #   .format(tax_line.tax_app_id.name)
                # )
            tax_journal = self.env['account.journal'].search(
                [('tax_id', '=', tax_line.retention_id.id)]
            )
            codigo_impuesto = (
                int(tax_journal.afip_code) if tax_journal.afip_code else 0
            )
            if not codigo_impuesto:
                raise UserError(
                    _(
                        "Error: Add field 'afip code' to retention\n"
                        "(Accounting->Configuration->Retentions->%s->AFIP Code)"
                    )
                    % tax_journal.name
                )
            line = {
                'codigo_comprobante': '06',
                # 06: Orden de pago; HARD: Todas las ret. salen de una op
                'fecha_emision': date_voucher,
                'numero_comprobante': internal_number,
                'monto_comprobante': self._format_monetary(amount_total),
                'codigo_impuesto': codigo_impuesto,
                'codigo_regimen': reg_code,
                'codigo_operacion': 1,  # Cod. Retenciones
                'base_calculo': self._format_monetary(base_amount),
                'fecha_emision_retenc': date_emited,
                'codigo_condicion': '01',  # Inscripto (HARD: Segun longport)
                'sujetos_suspend': '',  # Beneficiarios en el exterior
                'importe_retencion': self._format_monetary(ret_aplicada),
                'porcentaje_exclusion': self._format_monetary(
                    porcentaje_exclusion
                ),
                'fecha_emision_boletin': (
                    date_emited if porcentaje_exclusion != 0 else ""
                ),  # Solo si hay exclusion
                'tipo_documento_retenido': tipo_doc_retenido,
                'numero_documento_retenido': nro_doc_retenido,
                'numero_certificado_original': nro_cert_propio,
                'denominacion_ordenante': (
                    '' if is_local else tax_line.partner_id.name[:30]
                ),
                'acrecentamiento': '' if is_local else '0',  # Segun longport
                'cuit_pais_retenido': '' if is_local else '',  # TODO
                'cuit_ordenante': '' if is_local else '',  # TODO
            }

            # Apendeamos el registro
            fixed_width.update(**line)
            head_regs.append(fixed_width.line)

        # Chequeamos si hubo errores
        if len(head_file_errors):
            return head_file_errors, False

        # Retornar vacio si no hay lineas generadas
        if len(head_regs) < 1:
            return [], False

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

        f = open(head_filename, 'rb')  # rb to export with CRLF line terminators

        name_base = "SICORE_RET" if is_local else "SICORE_RET_EXT"
        name = ('%s_%s_%s.txt') % (
            name_base,
            self.period_start,
            self.company_id.name.replace(' ', '-'),
        )
        generated_file_rec = self.env['sicore.generated.files'].create(
            {
                'code': name,
                'period_start': self.period_start,
                'period_end': self.period_end,
                'presentation_date': self.presentation_date,
                'company_id': self.company_id.id,
            }
        )
        data = f.read()
        if isinstance(data, str):
            data = data.encode('ascii', 'replace')
        data_attach = {
            'name': name,
            'datas': binascii.b2a_base64(data),
            'store_fname': name,
            'res_model': 'sicore.generated.files',
            'res_id': generated_file_rec.id,
        }
        new_attachment = self.env['ir.attachment'].create(data_attach)
        generated_file_rec.write({'attachment_id': new_attachment.id})
        f.close()

        return [], True

    def create_files(self):
        self._validate_before_create()

        errors = ''
        cr = self._cr

        retention_query = (
            "SELECT r.id "
            "FROM account_payment_order_retention_line r "
            "JOIN account_tax at ON r.retention_id=at.id "
            "JOIN account_payment_order av ON av.id=r.payment_order_id "
            "WHERE r.date BETWEEN %(date_from)s AND %(date_to)s "
            "AND at.retention_type in ('vat','profit') AND at.type_tax_use='purchase' "
            "AND av.state ~ 'posted' AND r.company_id = %(company_id)s "
            "ORDER BY r.date"
        )

        cr.execute(
            retention_query,
            {
                'date_from': self.period_start,
                'date_to': self.period_end,
                'company_id': self.company_id.id,
            },
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
        retention_errors_local, success_local = self._generate_retention_file(
            retention_ids
        )
        retention_errors_ext, success_ext = self._generate_retention_file(
            retention_ids, exterior=True
        )
        created = (
            "LOCAL & EXT"
            if success_local and success_ext
            else (
                "LOCAL"
                if success_local
                else "EXT" if success_ext else "No success"
            )
        )

        if retention_errors_local or retention_errors_ext:
            errors += _('Retention File Errors\n================\n')
            errors += '\n'.join(retention_errors_local)
            errors += '\n'.join(retention_errors_ext)

        if errors:
            self.write({'notes': errors})
            form_id = self.env.ref('l10n_ar_eynes.view_create_sicore_files').id
            res = {
                'name': _('Sicore'),
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
        elif success_local or success_ext:
            message = _("SICORE Reports created: %s ") % (created)
            notification = {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': message,
                    'type': 'success',
                    'sticky': False,
                    'next': {'type': 'ir.actions.act_window_close'},
                },
            }
            return notification

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

        name = 'SICORE_RET_RRHH_%s_%s.txt' % (
            self.period_start,
            self.company_id.name.replace(' ', '-'),
        )
        generated_file_rec = self.env['sicore.generated.files'].create(
            {
                'code': name,
                'period_start': self.period_start,
                'period_end': self.period_end,
                'presentation_date': self.presentation_date,
                'company_id': self.company_id.id,
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

        name = 'SICORE_RET_RRHH_P_%s_%s.txt' % (
            self.period_start,
            self.company_id.name.replace(' ', '-'),
        )
        generated_file_rec = self.env['sicore.generated.files'].create(
            {
                'code': name,
                'period_start': self.period_start,
                'period_end': self.period_end,
                'presentation_date': self.presentation_date,
                'company_id': self.company_id.id,
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
            AND pl.state IN %(state)s AND psl.company_id = %(company_id)s
            GROUP BY pl.id, pl.employee_id, pl.date_to
        """
        q_params = {
            'state': tuple(['done']),
            # 'code': self.rrhh_ret_profit_code,
            'code': tuple([self.rrhh_ret_profit_code, 'H349']),
            'date_from': self.period_start,
            'date_to': self.period_end,
            'company_id': self.company_id.id,
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
