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
from odoo.tools.misc import formatLang

from ..utils.sicore_fixed_width import FixedWidth, moneyfmt
from ..utils.sicore_fixed_width_dicts import (
    HEAD_LINES,
    HEAD_LINES_PADRON,
    HEAD_LINES_RET_EXTERIOR,
    HEAD_LINES_RET_LOCAL,
)

_logger = logging.getLogger(__name__)

# Tabla de comprobantes de SICORE, para el comprobante que origina la
# percepcion: 01 Factura, 03 Nota de credito, 04 Nota de debito.
PERCEPTION_VOUCHER_CODES = {'b': 1, 'dn': 4, 'cn': 3}
CREDIT_NOTE_VOUCHER_CODE = 3

# Codigo de condicion usado cuando la posicion fiscal del cliente no esta
# mapeada en la configuracion de SICORE (01: Inscripto).
DEFAULT_CONDITION_CODE = '01'

# Las retenciones de IVA y de Ganancias se exportan en archivos separados.
RETENTION_TYPE_LABELS = {
    'vat': 'IVA',
    'profit': 'GANANCIAS',
}

# Codigo de condicion de percepciones y retenciones de IVA.
VAT_CONDITION_CODE = '13'


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
    include_vat_perceptions = fields.Boolean(
        'Include VAT perceptions',
        default=False,
        help="Include the VAT perceptions applied to customers in the "
        "generated file, informed as operation code 2 (perception).\n"
        "Requires the AFIP retention code to be set on the journal linked "
        "to the perception tax.",
    )

    @api.model
    def _default_company_ids(self):
        return json.dumps(
            [('id', 'in', self.env.context.get('allowed_company_ids', []))]
        )

    def _table_exists(self, table_name):
        self.env.cr.execute("SELECT to_regclass(%s)", (table_name,))
        return bool(self.env.cr.fetchone()[0])

    def _validate_before_create(self):
        if not self.period_start:
            raise UserError(_("You must enter 'start' date"))
        if not self.period_end:
            raise UserError(_("You must enter 'end' date"))

    def _format_monetary(self, value):
        return "{:,.2f}".format(value).replace(",", "")

    def _format_base_calculo(self, value):
        """La base de calculo omite el punto y los centavos si es entera."""
        rounded = round(value, 2)
        if rounded == int(rounded):
            return str(int(rounded))
        return self._format_monetary(rounded)

    @api.model
    def _get_reg_code(self, line):
        """Codigo de regimen: concept_id.code es texto libre (ej. "RG830"),
        se queda solo con los digitos."""
        tax_app = (
            line.tax_app_id
            if line._name == 'perception.tax.line'
            else line.taxapp_id
        )
        reg_code = line.reg_code or tax_app.reg_code or line.concept_id.code
        reg_code = re.sub(r"\D", "", str(reg_code))[:3] if reg_code else ''
        return reg_code or '0'

    @api.model
    def _generate_retention_file(
        self,
        retention_ids,
        exterior=False,
        perception_ids=None,
        retention_type_label='',
    ):
        head_file_errors = []
        head_regs = []
        fixed_width = (
            FixedWidth(HEAD_LINES_RET_LOCAL)
            if not exterior
            else FixedWidth(HEAD_LINES_RET_EXTERIOR)
        )
        is_local = not exterior

        tax_lines = self.env['account.payment.order.retention.line'].browse(
            retention_ids
        )

        # Sin proveedor no se puede armar el registro ni saber si va al
        # archivo local o al de exterior: se informa en que OP esta para que
        # la corrijan. Se reporta una sola vez, en la pasada del archivo local.
        no_partner_lines = tax_lines.filtered(lambda line: not line.partner_id)
        if is_local:
            for tax_line in no_partner_lines:
                order = tax_line.payment_order_id
                head_file_errors.append(
                    _(
                        "Payment order %(order)s of %(date)s: the retention "
                        "%(retention)s for %(amount)s has no partner. Check "
                        "the retentions of that payment order.",
                        order=order.number or order.reference or order.id,
                        date=order.date.strftime('%d/%m/%Y'),
                        retention=tax_line.retention_id.name or tax_line.name,
                        amount=formatLang(
                            self.env,
                            tax_line.amount,
                            currency_obj=order.currency_id,
                        ),
                    )
                )
        tax_lines -= no_partner_lines

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
            nro_doc_retenido = re.sub(r"\D", "", tax_line.partner_id.vat or '')

            # First search in number then in reference
            internal_number = tax_line.payment_order_id.number or ''
            if not internal_number:
                err = '%s: Número de comprobante no encontrado.' % line_ident
                head_file_errors.append(err)
                continue
            else:
                # La OP no tiene punto de venta: numero a 13 digitos.
                internal_number = re.sub(r"\D", "", internal_number).zfill(13)

            date_emited = tax_line.date.strftime('%d/%m/%Y')

            exclusion_date_certificate = tax_line.exclusion_date_certificate
            if exclusion_date_certificate:
                exclusion_date_certificate = (
                    exclusion_date_certificate.strftime('%d/%m/%Y')
                )
            else:
                exclusion_date_certificate = ''

            porcentaje_exclusion = tax_line.excluded_percent * 100

            # Importe del comprobante: como 'codigo_comprobante' es siempre
            # '06' (orden de pago), el importe que corresponde informar es el
            # total de la OP, incluyendo las retenciones.
            amount_total = tax_line.payment_order_id.amount
            # En las retenciones cargadas a mano base_amount se completa al
            # validar la OP con el total de la OP: se informa la base cargada.
            base_amount = (
                tax_line.base if tax_line.manual else tax_line.base_amount
            )
            ret_aplicada = tax_line.amount  # Importe retenido
            nro_cert_propio = re.sub(r"\D", "", tax_line.certificate_no or '')
            if nro_cert_propio:
                nro_cert_propio = nro_cert_propio.zfill(14)
            reg_code = self._get_reg_code(tax_line)
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
            # Ganancias toma la condicion de la posicion fiscal del proveedor.
            codigo_condicion = (
                self._get_sicore_condition_code(tax_line.partner_id)
                if retention_type_label == RETENTION_TYPE_LABELS['profit']
                else VAT_CONDITION_CODE
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
                'base_calculo': self._format_base_calculo(base_amount),
                'fecha_emision_retenc': date_emited,
                'codigo_condicion': codigo_condicion,
                'sujetos_suspend': '',  # Beneficiarios en el exterior
                'importe_retencion': self._format_monetary(ret_aplicada),
                'porcentaje_exclusion': (
                    self._format_monetary(porcentaje_exclusion)
                    if porcentaje_exclusion
                    else ''
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

        # Las percepciones se informan siempre en el archivo local: el layout
        # de exterior pide datos del ordenante que la percepcion no tiene.
        if is_local and perception_ids:
            perception_errors, perception_regs = self._get_perception_regs(
                fixed_width, perception_ids
            )
            head_file_errors += perception_errors
            head_regs += perception_regs

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
        if retention_type_label:
            name_base += "_%s" % retention_type_label
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

    def _search_perception_ids(self):
        """Percepciones de IVA efectuadas a clientes dentro del periodo.

        Se filtra por la fecha del comprobante (invoice_date) y no por
        perception_tax_line.date: esta ultima es un snapshot que se toma una
        sola vez y puede quedar desactualizado si el comprobante se refecha
        despues (ver T17401).
        """
        query = (
            "SELECT ptl.id "
            "FROM perception_tax_line ptl "
            "JOIN account_move am ON ptl.invoice_id = am.id "
            "JOIN account_tax at ON ptl.perception_id = at.id "
            "WHERE am.invoice_date BETWEEN %(date_from)s AND %(date_to)s "
            "AND am.state = 'posted' "
            "AND at.retention_type = 'vat' AND at.type_tax_use = 'sale' "
            "AND am.company_id = %(company_id)s "
            "ORDER BY am.invoice_date"
        )
        self.env.cr.execute(
            query,
            {
                'date_from': self.period_start,
                'date_to': self.period_end,
                'company_id': self.company_id.id,
            },
        )
        return [row[0] for row in self.env.cr.fetchall()]

    def _get_perception_afip_code(self, perception_tax):
        """Codigo de impuesto SICORE: el cargado en la percepcion o, si no,
        el del diario de la percepcion."""
        if perception_tax.sicore_tax_code:
            return int(perception_tax.sicore_tax_code)
        journal = self.env['account.journal'].search(
            [
                ('tax_id', '=', perception_tax.id),
                ('company_id', '=', self.company_id.id),
            ],
            limit=1,
        )
        return int(journal.afip_code) if journal.afip_code else 0

    def _get_sicore_condition_code(self, partner):
        """Codigo de condicion del sujeto percibido segun su posicion fiscal.

        Usa el mapeo de Contabilidad->Configuracion->SICORE. Si la posicion
        fiscal del cliente no esta mapeada, se informa como inscripto.
        """
        fiscal_position = partner.property_account_position_id
        sicore_fiscal_position = self.env['sicore.fiscal.position'].search(
            [('fiscal_position', '=', fiscal_position.id)], limit=1
        )
        code = sicore_fiscal_position.code or DEFAULT_CONDITION_CODE
        return code.zfill(2)

    def _get_perception_regs(self, fixed_width, perception_ids):
        """Arma los registros SICORE de las percepciones de IVA efectuadas.

        Devuelve (errores, registros). Los errores no cortan la generacion:
        se acumulan para mostrarlos juntos en el recuadro de validacion del
        asistente y que el usuario corrija toda la configuracion de una vez.
        """
        errors = []
        regs = []
        afip_code_by_tax = {}

        perception_lines = self.env['perception.tax.line'].browse(
            perception_ids
        )
        for perception in perception_lines:
            invoice = perception.invoice_id
            line_ident = 'Perception Tax Line #%s of Invoice %s' % (
                perception.id,
                invoice.name or invoice.id,
            )
            _logger.info(line_ident)

            codigo_comprobante = PERCEPTION_VOUCHER_CODES.get(
                invoice.voucher_type_id.doc_type
            )
            if not codigo_comprobante:
                errors.append(
                    _('%s: Voucher type not found on the invoice.') % line_ident
                )
                continue

            # Punto de venta (5) + numero (8), cada parte con sus ceros.
            try:
                pos_code, seq_number = (invoice.name or '').split('-')
                numero_comprobante = pos_code.zfill(5) + re.sub(
                    r"\D", "", seq_number
                ).zfill(8)
            except ValueError:
                numero_comprobante = ''
            if not numero_comprobante:
                errors.append(_('%s: Invoice number not found.') % line_ident)
                continue

            partner = perception.partner_id
            tipo_doc_percibido = partner.document_type_id.afip_code
            nro_doc_percibido = re.sub(r"\D", "", partner.vat or '')
            if not tipo_doc_percibido or not nro_doc_percibido:
                errors.append(
                    _('%s: Document type or VAT not found for partner %s.')
                    % (line_ident, partner.name)
                )
                continue

            perception_tax = perception.perception_id
            if perception_tax.id not in afip_code_by_tax:
                afip_code_by_tax[perception_tax.id] = (
                    self._get_perception_afip_code(perception_tax)
                )
            codigo_impuesto = afip_code_by_tax[perception_tax.id]
            if not codigo_impuesto:
                errors.append(
                    _(
                        "%s: Add field 'AFIP retention code' to the journal "
                        "of the perception '%s'\n"
                        "(Accounting->Configuration->Journals)"
                    )
                    % (line_ident, perception_tax.name)
                )
                continue

            reg_code = self._get_reg_code(perception)

            date_invoice = invoice.invoice_date.strftime('%d/%m/%Y')

            # En notas de credito SICORE toma la base de calculo como el
            # importe a favor del contribuyente: la percepcion que se anula.
            base_calculo = (
                abs(perception.amount)
                if codigo_comprobante == CREDIT_NOTE_VOUCHER_CODE
                else perception.base
            )

            line = {
                'codigo_comprobante': codigo_comprobante,
                'fecha_emision': date_invoice,
                'numero_comprobante': numero_comprobante,
                'monto_comprobante': self._format_monetary(
                    invoice.amount_total
                ),
                'codigo_impuesto': codigo_impuesto,
                'codigo_regimen': reg_code,
                'codigo_operacion': 2,  # Cod. Percepciones
                'base_calculo': self._format_base_calculo(base_calculo),
                # La percepcion se practica al emitir el comprobante.
                'fecha_emision_retenc': date_invoice,
                'codigo_condicion': VAT_CONDITION_CODE,
                'sujetos_suspend': '',  # Beneficiarios en el exterior
                'importe_retencion': self._format_monetary(perception.amount),
                # Las percepciones no manejan certificado de exclusion.
                'porcentaje_exclusion': '',
                'fecha_emision_boletin': '',
                'tipo_documento_retenido': str(tipo_doc_percibido),
                'numero_documento_retenido': nro_doc_percibido,
                'numero_certificado_original': '',
            }

            # Apendeamos el registro
            fixed_width.update(**line)
            regs.append(fixed_width.line)

        return errors, regs

    def create_files(self):
        self._validate_before_create()

        errors = ''
        cr = self._cr

        retention_query = (
            "SELECT r.id, at.retention_type "
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
        retention_ids_by_type = {key: [] for key in RETENTION_TYPE_LABELS}
        for retention_id, retention_type in res:
            retention_ids_by_type[retention_type].append(retention_id)

        perception_ids = []
        if self.include_vat_perceptions:
            perception_ids = self._search_perception_ids()

        if not res and not perception_ids:
            message = _(
                """Export Error
                    Applicable Retentions for export not found.
                    HINT:
                    The retention is of type vat or profit ?"""
            )
            if self.include_vat_perceptions:
                message += _(
                    "\nNo VAT perceptions were found either. "
                    "Are the invoices with perceptions posted?"
                )
            raise UserError(message)

        # Un archivo por tipo de retencion; las percepciones de IVA van en el
        # archivo de IVA.
        created = []
        for retention_type, label in RETENTION_TYPE_LABELS.items():
            type_retention_ids = retention_ids_by_type[retention_type]
            type_perception_ids = (
                perception_ids if retention_type == 'vat' else None
            )
            if not type_retention_ids and not type_perception_ids:
                continue
            errors_local, success_local = self._generate_retention_file(
                type_retention_ids,
                perception_ids=type_perception_ids,
                retention_type_label=label,
            )
            errors_ext, success_ext = self._generate_retention_file(
                type_retention_ids,
                exterior=True,
                retention_type_label=label,
            )
            if errors_local or errors_ext:
                errors += (
                    _('Retention File Errors (%s)\n================\n') % label
                )
                errors += '\n'.join(errors_local + errors_ext) + '\n'
            if success_local:
                created.append(label)
            if success_ext:
                created.append('%s EXT' % label)

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
        elif created:
            message = _("SICORE Reports created: %s ") % ', '.join(created)
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
        if not (
            self._table_exists('hr_payslip')
            and self._table_exists('hr_payslip_line')
        ):
            raise UserError(
                _(
                    'Export Error\n'
                    'The RRHH SICORE export requires the Payroll module '
                    'to be installed in this database.'
                )
            )
        errors = ''

        q = """
            SELECT pl.id payslip_id, pl.employee_id employee_id,
            SUM(psl.total) total FROM hr_payslip_line AS psl
            JOIN hr_payslip AS pl ON (pl.id=psl.slip_id)
            WHERE psl.code IN %(code)s AND pl.date BETWEEN
            %(date_from)s AND %(date_to)s AND psl.total!=0
            AND pl.state IN %(state)s AND pl.company_id = %(company_id)s
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
