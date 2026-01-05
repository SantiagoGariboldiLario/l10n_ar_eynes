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
from odoo.exceptions import ValidationError

from ..utils.arciba_fixed_width_dicts import HEAD_LINES, HEAD_LINES_NC
from ..utils.sicore_fixed_width import FixedWidth, moneyfmt

logger = logging.getLogger(__name__)


class CreateArcibaFiles(models.TransientModel):
    _name = 'create.arciba.files'
    _description = 'Wizard Create e-arciba Files'

    company_id = fields.Many2one('res.company', required=True)
    company_id_domain = fields.Char(
        default=lambda self: self._default_company_ids()
    )
    period_start = fields.Date('Date start')
    period_end = fields.Date('Date end')
    notes = fields.Text('Notes')

    @api.model
    def _default_company_ids(self):
        return json.dumps(
            [('id', 'in', self.env.context.get('allowed_company_ids', []))]
        )

    @api.model
    def _get_partner_document_type_code(self, partner):
        document_type_name = partner.document_type_id.name
        dict_types = {'CUIT': 3, 'CUIL': 2, 'CDI': 1}
        code_document_type = dict_types.get(document_type_name, False)
        if not code_document_type:
            raise ValidationError(
                _(
                    'Arciba Code not found for document_type_name: %(doc_type)s  on %(partner_name)s.'
                    ' You must use CUIT/CUIL',
                    doc_type=document_type_name,
                    partner_name=partner.name,
                )
            )
        return code_document_type

    @api.model
    def _get_partner_iibb_code(self, iibb):
        dict_types = {
            self.env.ref('l10n_ar_eynes.iibb_situation_local'): 1,
            self.env.ref('l10n_ar_eynes.iibb_situation_multilateral'): 2,
            self.env.ref('l10n_ar_eynes.iibb_situation_not_inscribed'): 4,
            self.env.ref('l10n_ar_eynes.iibb_situation_simplified_regime'): 5,
        }
        code_iibb = dict_types.get(iibb, False)
        return code_iibb

    @api.model
    def _get_partner_fiscal_position_code(self, inv):
        code_fiscal_position = inv.fiscal_position_id.afip_code
        if not code_fiscal_position:
            raise ValidationError(
                _(
                    "Fiscal position '%(name)s' doesn't have AFIP code configured",
                    name=inv.fiscal_position_id.name,
                )
            )
        if (
            code_fiscal_position
            == self.env.ref('l10n_ar_eynes.fiscal_position_rem').afip_code
        ):
            code_fiscal_position = 4
        elif code_fiscal_position in [
            self.env.ref('l10n_ar_eynes.fiscal_position_se').afip_code,
        ]:
            code_fiscal_position = 3
        return code_fiscal_position

    def generate_fw_file(self, data_lst):
        self.ensure_one()
        generated_files_model = self.env['arciba.generated.files']
        fixed_width = FixedWidth(HEAD_LINES)
        head_regs = []

        for line in data_lst:
            # Apendeamos el registro
            fixed_width.update(**line)
            head_regs.append(fixed_width.line)

        head_filename = tempfile.mkstemp(suffix='.arciba')[1]
        f = codecs.open(head_filename, "w", "utf-8")

        for r in head_regs:
            r2 = [a for a in r]
            try:
                f.write(''.join(r2))
            except Exception as e:
                raise e
            f.write('\r\n')

        f.close()

        f = codecs.open(head_filename, "r", "utf-8")

        name = 'eARCIBA_%s_%s.txt' % (
            self.period_start,
            self.company_id.name.replace(' ', '-'),
        )
        generated_file_rec = generated_files_model.create(
            {
                'code': name,
                'date_from': self.period_start,
                'date_to': self.period_end,
                'company_id': self.company_id.id,
            }
        )

        data_attach = {
            'name': name,
            'datas': binascii.b2a_base64(f.read().encode('utf-8')),
            # 'datas_fname': name,
            'res_model': 'arciba.generated.files',
            'res_id': generated_file_rec.id,
        }
        doc = self.env['ir.attachment'].create(data_attach)
        generated_file_rec.write({'attachment_id': doc.id})

        return True

    def _get_invoice_tax_lines(self, invoice):
        tax_line_ids = invoice.line_ids.filtered(lambda line: line.tax_line_id)
        return tax_line_ids

    def _get_invoice_vat_tax_lines(self, invoice):
        tax_line_ids = self._get_invoice_tax_lines(invoice).filtered(
            lambda line: line.tax_line_id.tax_group_id.group_type == 'vat'
        )
        return tax_line_ids

    def _get_invoice_iva_total(self, invoices):
        """
        Expects an invoice and return total amount of iva tax
        """
        iva_amount = 0
        for inv in invoices:
            iva_lines = self._get_invoice_vat_tax_lines(inv)
            # iva_amount += sum(iva_lines.mapped('price_unit'))
            for line in iva_lines:
                iva_amount += line.debit + line.credit

        return iva_amount

    @api.model
    def _get_ret_data(self, retention_ids):
        """
        Iterates on retentions and retrieve data to compose the txt.
        """
        ret_obj = self.env['account.payment.order.retention.line']
        res = []
        errors = []
        for ret in ret_obj.browse(retention_ids):
            # **-------**  Datos desde la Retención: **--------**
            # Ret Date
            date_val = time.strptime(
                str(ret.date), '%Y-%m-%d'
            )  # String(YYYY-MM-DD)->Datetime
            date_val = time.strftime(
                '%d/%m/%Y', date_val
            )  # Datetime->String: dd/mm/yyyy
            # Nro Cert
            nro_cert_propio = ret.certificate_no or '0000000000000000'
            # Ret / Per applied
            ret_per_applied = ret.amount
            # Ret / Per base
            base_amount = ret.base_amount

            # **-------**  Datos desde la Orden de Pago: **--------**
            op = ret.payment_order_id
            partner = op.partner_id
            # Alicuota
            percentage = (
                self.env["res.partner.retention"]
                .search(
                    [
                        ("retention_id", "=", ret.retention_id.id),
                        ("partner_id", "=", partner.id),
                        ("period", "=", self.period_start),
                    ]
                )
                .percent
            )
            if percentage < 0 or percentage > 99.99:
                errors.append(
                    _(
                        'rtl #%(ret_id)s: Percentage cannot be negative or '
                        'more than 99.99 (%(ret_name)s) (OP ID %(op_id)s)',
                        ret_id=ret.id,
                        ret_name=ret.name,
                        op_id=ret.voucher_number,
                    )
                )
                continue
            elif percentage != 0.0:
                # Type of document partner
                nro_doc_retenido = (
                    partner.vat.replace('-', '')
                    if partner.vat
                    else '00000000000'
                )
                try:
                    tipo_doc_retenido = self._get_partner_document_type_code(
                        partner
                    )
                except Exception as e:
                    errors.append(str(e))
                    continue
                # Voucher date
                voucher_date = time.strptime(
                    str(op.date), '%Y-%m-%d'
                )  # String(YYYY-MM-DD)->Datetime
                voucher_date = time.strftime(
                    '%d/%m/%Y', voucher_date
                )  # Datetime->String: dd/mm/yyyy
                # Internal number
                voucher_number = re.sub(r"\D", "", op.number)
                # Partner Data
                pos_fiscal_retenido = (
                    partner.property_account_position_id.afip_code
                )
                if pos_fiscal_retenido in [
                    self.env.ref('l10n_ar_eynes.fiscal_position_rem').afip_code,
                    self.env.ref('l10n_ar_eynes.fiscal_position_ms').afip_code,
                ]:
                    pos_fiscal_retenido = 4
                elif pos_fiscal_retenido in [
                    self.env.ref('l10n_ar_eynes.fiscal_position_se').afip_code,
                ]:
                    pos_fiscal_retenido = 3
                else:
                    pos_fiscal_retenido = 1

                razon_social_retenido = (
                    (partner.name).replace('ñ', 'n').replace('Ñ', 'N')
                )
                # IIBB
                ppids = partner.retention_ids
                ret_partner = ppids.filtered(
                    lambda x: x.retention_id == ret.retention_id
                )
                ret_partner = (
                    ret_partner[0] if len(ret_partner) > 1 else ret_partner
                )
                sit_iibb = self._get_partner_iibb_code(ret_partner.sit_iibb)
                if not sit_iibb:
                    errors.append(
                        _(
                            'rtl #%(ret_id)s: IIBB Situation cannot be empty'
                            ' (%(ret_name)s) (Partner %(part_name)s)',
                            ret_id=ret.id,
                            ret_name=ret.name,
                            part_name=razon_social_retenido,
                        )
                    )

                # **-------**  Datos desde las Facturas: **--------**
                op_lines = op.debt_line_ids.filtered(
                    lambda line: line.amount != 0
                )
                invoices = op_lines.mapped('invoice_id')
                if not len(invoices):
                    errors.append(
                        _(
                            'rtl #%(ret_id)s: Unable to get associated invoice (%(ret_name)s)',
                            ret_id=ret.id,
                            ret_name=ret.name,
                        )
                    )
                    continue
                # Denomination
                denomination_name = ''
                # Invoice total
                op_amount_total = sum(op_lines.mapped('amount'))
                # Iva Amount
                inv_iva_amount = 0.0
                # # Monto de otros conceptos:
                amount_others = op_amount_total - inv_iva_amount - base_amount

                line = {
                    'type': 1,  # Retention
                    'codigo_norma': 29,  # NUEVO: PADRÓN DE REGIMENES GENERALES
                    'fecha': date_val,
                    'tipo_comp_origen_retenc': "03",  # Account Voucher (We pay to supplier)
                    'letra_comprobante': denomination_name,
                    'numero_comprobante': voucher_number,
                    'fecha_comprobante': voucher_date,
                    'monto_comprobante': moneyfmt(
                        Decimal(op_amount_total), places=2, ndigits=13, dp=','
                    ),
                    'nro_cert_propio': str(nro_cert_propio),
                    'tipo_doc_retenido': tipo_doc_retenido,
                    'nro_doc_retenido': nro_doc_retenido,
                    # 'sit_iibb_retenido': sit_iibb,
                    'sit_iibb_retenido': 2,
                    'nro_insc_iibb_retenido': nro_doc_retenido,
                    'pos_fiscal_retenido': pos_fiscal_retenido,
                    'razon_social_retenido': razon_social_retenido,
                    'importe_otros_conceptos': moneyfmt(
                        Decimal(amount_others), places=2, ndigits=13, dp=','
                    ),
                    'importe_iva': moneyfmt(
                        Decimal(inv_iva_amount), places=2, ndigits=13, dp=','
                    ),
                    'monto_sujeto_a_ret_per': moneyfmt(
                        Decimal(base_amount), places=2, ndigits=13, dp=','
                    ),
                    'alicuota': moneyfmt(
                        Decimal(percentage), places=2, ndigits=4, dp=','
                    ),
                    'ret_per_aplicada': moneyfmt(
                        Decimal(ret_per_applied), places=2, ndigits=13, dp=','
                    ),
                    'monto_total_ret_per': moneyfmt(
                        Decimal(ret_per_applied), places=2, ndigits=13, dp=','
                    ),
                    'aceptacion': '',  # Para comprobantes mipyme
                    'fecha_aceptacion': '',  # Para comprobantes mipyme
                }
                res.append(line)
        if not errors:
            return None, res
        else:
            return 1, errors

    @api.model
    def _get_perc_data(self, perc_ids):
        """
        Iterates over invoices looking for perceptions and retrieve neccesary data
        as a dict.
        """
        perc_obj = self.env['perception.tax.line']
        res = []
        errors = []
        for perc in perc_obj.browse(perc_ids):
            inv = perc.invoice_id
            if not inv:
                errors.append(
                    _(
                        'ptl #%(per_id)s: Unable to get associated invoice (%(inv_id)s)',
                        per_id=perc.id,
                        inv_id=inv.id,
                    )
                )
                continue

            # Date
            date_val = time.strptime(
                str(perc.date), '%Y-%m-%d'
            )  # String(YYYY-MM-DD)->Datetime
            date_val = time.strftime(
                '%d/%m/%Y', date_val
            )  # Datetime->String: dd/mm/yyyy

            # Date invoice
            date_inv = time.strptime(
                str(inv.invoice_date), '%Y-%m-%d'
            )  # String(YYYY-MM-DD)->Datetime
            date_inv = time.strftime(
                '%d/%m/%Y', date_inv
            )  # Datetime->String: dd/mm/yyyy

            # Denomination
            denomination_name = inv.denomination.upper()

            # Internal number
            internal_number = re.sub(r'\D', '', inv.internal_number)

            # Invoice total
            # inv_amount_total = inv.amount_total
            inv_amount_total = abs(inv.amount_total_signed)

            # Type of document partner
            nro_doc_retenido = (
                inv.partner_id.vat.replace('-', '')
                if inv.partner_id.vat
                else '00000000000'
            )
            try:
                tipo_doc_retenido = self._get_partner_document_type_code(
                    inv.partner_id
                )
            except Exception as e:
                errors.append(str(e))
                continue

            # Ret / Per applied
            # ret_per_applied = perc.amount
            ret_per_applied = 0
            if inv.company_id.currency_id == inv.currency_id:
                ret_per_applied = perc.amount
            else:
                # ((perc.amount / perc.base) * 100) redondeado a 2
                ret_per_applied = (
                    round(((perc.amount / perc.base) * 100), 2)
                    / 100
                    * perc.base_secondary_currency
                )

            # Ret / Per base
            base_amount = (
                perc.base
                if inv.company_id.currency_id == inv.currency_id
                else perc.base_secondary_currency
            )

            # Alicuota
            percentage = round(ret_per_applied / base_amount * 100, 2)
            if percentage < 0 or percentage > 99.99:
                errors.append(
                    _(
                        'ptl #%(per_id)s: Percentage cannot be negative or '
                        'more than 99.99 (%(per_name)s) (Invoice ID %(inv_id)s)',
                        per_id=perc.id,
                        per_name=perc.name,
                        inv_id=inv.id,
                    )
                )
                continue

            # Iva Amount
            inv_iva_amount = 0.0
            if denomination_name in ('A', 'M'):
                inv_iva_amount = self._get_invoice_iva_total(inv)

            amount_others = abs(
                round(inv_amount_total - inv_iva_amount - base_amount, 2)
            )

            # Partner Data
            pos_fiscal_retenido = self._get_partner_fiscal_position_code(inv)
            razon_social_retenido = (
                (inv.partner_id.name).replace('ñ', 'n').replace('Ñ', 'N')
            )

            # IIBB
            ppids = perc.partner_id.perception_ids
            perc_partner = ppids.filtered(
                lambda x: x.perception_id == perc.perception_id
            )
            perc_partner = (
                perc_partner[0] if len(perc_partner) > 1 else perc_partner
            )
            sit_iibb = self._get_partner_iibb_code(perc_partner.sit_iibb)
            if not perc_partner:
                # Forzamos esto por el caso de Tommasi, que cambiaron la posición fiscal de los clientes
                # y quedaron percepciones practicadas a gente que era de otra jurisdicción.
                sit_iibb = self._get_partner_iibb_code(
                    self.env.ref('l10n_ar_eynes.iibb_situation_local')
                )
            if not sit_iibb:
                errors.append(
                    _(
                        'ptl #%(per_id)s: IIBB Situation cannot be'
                        ' empty (%(per_name)s) (Partner %(part_name)s)',
                        per_id=perc.id,
                        per_name=perc.name,
                        part_name=razon_social_retenido,
                    )
                )

            line = {
                'type': 2,  # Perception
                'codigo_norma': 29,  # NUEVO: PADRÓN DE REGIMENES GENERALES
                'fecha': date_val,
                'tipo_comp_origen_retenc': "01",  # Invoice
                'letra_comprobante': denomination_name,
                'numero_comprobante': internal_number,
                'fecha_comprobante': date_inv,
                'monto_comprobante': moneyfmt(
                    Decimal(inv_amount_total), places=2, ndigits=13, dp=','
                ),
                'nro_cert_propio': '',  # In perceptions this field is blank
                'tipo_doc_retenido': tipo_doc_retenido,
                'nro_doc_retenido': nro_doc_retenido,
                # 'sit_iibb_retenido': sit_iibb,
                'sit_iibb_retenido': 2,
                'nro_insc_iibb_retenido': nro_doc_retenido,
                'pos_fiscal_retenido': pos_fiscal_retenido,
                'razon_social_retenido': razon_social_retenido,
                'importe_otros_conceptos': moneyfmt(
                    Decimal(amount_others), places=2, ndigits=13, dp=','
                ),
                'importe_iva': moneyfmt(
                    Decimal(inv_iva_amount), places=2, ndigits=13, dp=','
                ),
                'monto_sujeto_a_ret_per': moneyfmt(
                    Decimal(base_amount), places=2, ndigits=13, dp=','
                ),
                'alicuota': moneyfmt(
                    Decimal(percentage), places=2, ndigits=4, dp=','
                ),
                'ret_per_aplicada': moneyfmt(
                    Decimal(ret_per_applied), places=2, ndigits=13, dp=','
                ),
                'monto_total_ret_per': moneyfmt(
                    Decimal(ret_per_applied), places=2, ndigits=13, dp=','
                ),
                'aceptacion': '',  # Para comprobantes mipyme
                'fecha_aceptacion': '',  # Para comprobantes mipyme
            }
            res.append(line)

        if not errors:
            return None, res
        else:
            return 1, errors

    def create_files(self):
        """
        Entrypoint to exporter
        """
        errors = ''
        cr = self.env.cr
        # Buscamos las perception_tax_line del periodo pedido
        # ordenados segun lo escrito en documento tecnico agip
        # El archivo de importación debe estar ordenado por fecha de percepcion

        perception_query = """
            SELECT p.id
            FROM perception_tax_line p
            JOIN account_move i ON p.invoice_id = i.id
            JOIN account_tax at ON p.perception_id = at.id
            WHERE p.date BETWEEN %(period_start)s AND %(period_end)s
            AND p.company_id = %(company_id)s
            AND i.state = %(state)s
            AND at.inform_arciba=True
            AND at.type_tax_use LIKE 'sale'  -- Only perceptions applied
            AND i.move_type IN ('out_invoice')  -- Not including refunds(NC)
            ORDER BY p.date """

        query_vals = {
            'period_start': self.period_start,
            'period_end': self.period_end,
            'state': 'posted',
            'company_id': self.company_id.id,
        }
        cr.execute(perception_query, query_vals)
        res = cr.fetchall()
        try:
            assert (
                len(res) > 0
            ), 'Expected at least 1 perception_tax_line, got %s' % len(res)
        except BaseException:
            perception_errors = False
            perception_vals = []
            logger.warning('No perceptions to export')
        else:
            perception_ids = [perception_ids[0] for perception_ids in res]
            perception_errors, perception_vals = self._get_perc_data(
                perception_ids
            )

        if perception_errors:
            errors += _('Perception File Errors\n================\n')
            errors += '\n'.join(perception_vals)
            errors += '\n\n\n'

        # Buscamos las retention_tax_line del periodo pedido
        # ordenados segun lo escrito en documento tecnico agip
        # El archivo de importación debe estar ordenado por fecha de retención

        retention_query = """
            SELECT p.id
            FROM account_payment_order_retention_line p
            JOIN account_payment_order op ON p.payment_order_id = op.id
            JOIN account_tax at ON p.retention_id = at.id
            WHERE p.date BETWEEN %(period_start)s AND %(period_end)s
            AND p.company_id = %(company_id)s
            AND op.state = %(state)s
            AND at.inform_arciba=True
            AND at.type_tax_use LIKE 'purchase'  -- Only retentions applied
            ORDER BY p.date
        """

        cr.execute(retention_query, query_vals)
        res = cr.fetchall()

        try:
            assert (
                len(res) > 0
            ), 'Expected at least 1 retention_tax_line, got %s' % len(res)
        except BaseException:
            retention_errors = False
            retention_vals = []
            logger.warning('No retentions to export')
        else:
            retention_ids = [retention_ids[0] for retention_ids in res]
            retention_errors, retention_vals = self._get_ret_data(retention_ids)

        if retention_errors:
            errors += _('Retention File Errors\n================\n')
            errors += '\n'.join(retention_vals)

        if errors:
            self.write({'notes': errors})
            form_res = self.env.ref('l10n_ar_eynes.view_create_arciba_files')
            form_id = form_res and form_res.id or False
            res = {
                'name': _('Arciba'),
                'view_type': 'form',
                'view_mode': 'form',
                'views': [
                    (form_id, 'form'),
                ],
                'res_model': 'create.arciba.files',
                'res_id': self.id,
                'view_id': form_id,
                'type': 'ir.actions.act_window',
                'target': 'new',
            }
        else:
            data_lst = retention_vals + perception_vals
            data_lst_sorted = sorted(data_lst, key=lambda x: x['fecha'])
            if data_lst:
                res = self.generate_fw_file(data_lst_sorted)
            else:
                raise ValidationError(
                    _(
                        "No perceptions/retentions from %(start)s to %(end)s to inform eArciba.",
                        start=self.period_start,
                        end=self.period_end,
                    )
                )
        return res


class CreateArcibaNcFile(models.TransientModel):
    _name = 'create.arciba.nc.file'
    _description = 'Wizard Create e-ARCIBA NC File'

    company_id = fields.Many2one('res.company', required=True)
    company_id_domain = fields.Char(
        default=lambda self: self._default_company_ids()
    )
    period_start = fields.Date('Date start')
    period_end = fields.Date('Date end')
    notes = fields.Text('Notes')

    @api.model
    def _default_company_ids(self):
        return json.dumps(
            [('id', 'in', self.env.context.get('allowed_company_ids', []))]
        )

    @api.model
    def _get_inv_data(self, perc_ids):
        """
        Iterates over invoices looking for perceptions and retrieve neccesary data
        as a dict.
        """
        perc_obj = self.env['perception.tax.line']
        res = []
        errors = []
        for perc in perc_obj.browse(perc_ids):
            inv = perc.invoice_id
            if not inv:
                errors.append(
                    _(
                        'ptl #%(per_id)s: Unable to get associated invoice (%(per_name)s)',
                        per_id=perc.id,
                        per_name=perc.name,
                    )
                )
                continue

            # Date invoice
            date_inv = time.strptime(
                str(inv.invoice_date), '%Y-%m-%d'
            )  # String(YYYY-MM-DD)->Datetime
            date_inv = time.strftime(
                '%d/%m/%Y', date_inv
            )  # Datetime->String: dd/mm/yyyy

            # Denomination
            denomination_name = inv.denomination.upper()

            # Internal number
            internal_number = re.sub(r'\D', '', inv.internal_number)

            # Perception base
            inv_base = (
                perc.base
                if inv.company_id.currency_id == inv.currency_id
                else perc.base_secondary_currency
            )

            # Type of document partner
            nro_doc_retenido = inv.partner_id.vat.replace('-', '')

            # Ret / Per applied
            ret_per_applied = perc.amount

            # Alicuota
            percentage = round(ret_per_applied / inv_base * 100, 2)
            if percentage < 0 or percentage > 99.99:
                errors.append(
                    _(
                        'ptl #%(per_id)s: Percentage cannot be negative or '
                        'more than 99.99 (%(per_name)s) (Invoice ID %(inv_id)s)',
                        per_id=perc.id,
                        per_name=perc.name,
                        inv_id=inv.id,
                    )
                )
                continue

            # Origin Voucher
            origin_voucher = ''
            date_val = ''
            # Date original percep
            if inv.associated_inv_ids:
                origin_voucher = str(
                    inv.associated_inv_ids[0].name.replace('-', '')[1:]
                )
                date_val = time.strptime(
                    str(inv.associated_inv_ids[0].date), '%Y-%m-%d'
                )  # String(YYYY-MM-DD)->Datetime
            elif inv.inform_period_date_from:
                origin_voucher = time.strptime(
                    str(inv.inform_period_date_from), '%Y-%m-%d'
                )  # String(YYYY-MM-DD)->Datetime
                date_val = origin_voucher
                origin_voucher = time.strftime(
                    '%d%m%Y', origin_voucher
                )  # Datetime->String: ddmmyyyy

            date_val = time.strftime(
                '%d/%m/%Y', date_val
            )  # Datetime->String: dd/mm/yyyy

            line = {
                'type': 2,  # Perception
                'nro_nc': internal_number,
                'fecha_nc': date_inv,
                'monto_nc': moneyfmt(
                    Decimal(inv_base), places=2, ndigits=13, dp=','
                ),
                'nro_cert_propio': '',  # In perceptions this field is blank
                'tipo_comp_origen_retenc': "01",  # Invoice
                'letra_comprobante': denomination_name,
                'nro_comprobante': origin_voucher,
                'nro_doc_retenido': nro_doc_retenido,
                'codigo_norma': 29,  # NUEVO: PADRÓN DE REGIMENES GENERALES
                'fecha_ret_per': date_val,
                'ret_per_a_deducir': moneyfmt(
                    Decimal(ret_per_applied), places=2, ndigits=13, dp=','
                ),
                'alicuota': moneyfmt(
                    Decimal(percentage), places=2, ndigits=4, dp=','
                ),
            }
            res.append(line)

        if not errors:
            return None, res
        else:
            return 1, errors

    def generate_fw_file(self, data_lst):
        self.ensure_one()
        generated_files_model = self.env['arciba.generated.files']
        fixed_width = FixedWidth(HEAD_LINES_NC)
        head_regs = []

        for line in data_lst:
            # Apendeamos el registro
            fixed_width.update(**line)
            head_regs.append(fixed_width.line)

        head_filename = tempfile.mkstemp(suffix='.arciba')[1]
        f = codecs.open(head_filename, "w", "utf-8")
        for r in head_regs:
            r2 = [a for a in r]
            try:
                f.write(''.join(r2))
            except Exception as e:
                raise e
            f.write('\r\n')

        f.close()
        f = codecs.open(head_filename, 'r', "utf-8")

        name = 'eARCIBA_NC_%s_%s.txt' % (
            self.period_start,
            self.company_id.name.replace(' ', '-'),
        )
        generated_file_rec = generated_files_model.create(
            {
                'code': name,
                'date_from': self.period_start,
                'date_to': self.period_end,
                'company_id': self.company_id.id,
            }
        )

        data_attach = {
            'name': name,
            'datas': binascii.b2a_base64(f.read().encode('utf-8')),
            # 'datas_fname': name,
            'res_model': 'arciba.generated.files',
            'res_id': generated_file_rec.id,
        }
        doc = self.env['ir.attachment'].create(data_attach)
        generated_file_rec.write({'attachment_id': doc.id})

        return True

    def create_files(self):
        """
        Entrypoint to exporter
        """
        errors = ''
        cr = self.env.cr

        # Buscamos las perception_tax_line del periodo pedido
        # ordenados segun lo escrito en documento tecnico agip
        # El archivo de importación debe estar ordenado por fecha de percepcion

        perception_query = """
            SELECT p.id
            FROM perception_tax_line p
            JOIN account_move i ON p.invoice_id = i.id
            JOIN account_tax at ON p.perception_id = at.id
            WHERE p.date BETWEEN %(period_start)s AND %(period_end)s
            AND p.company_id = %(company_id)s
            AND i.state = %(state)s
            AND at.inform_arciba=True
            AND at.type_tax_use LIKE 'sale'  -- Only perceptions applied
            AND i.move_type IN ('out_refund')  -- Only including refunds(NC)
            ORDER BY p.date """

        query_vals = {
            'period_start': self.period_start,
            'period_end': self.period_end,
            'state': 'posted',
            'company_id': self.company_id.id,
        }

        cr.execute(perception_query, query_vals)
        res = cr.fetchall()
        try:
            assert (
                len(res) > 0
            ), 'Expected at least 1 perception_tax_line, got %s' % len(res)
        except BaseException:
            perception_errors = False
            perception_vals = []
            logger.warning('No perceptions to export')
        else:
            inv_ids = [inv_id[0] for inv_id in res]  # Fixed list
            perception_errors, perception_vals = self._get_inv_data(inv_ids)

        if perception_errors:
            errors += _('Perception File Errors\n================\n')
            errors += '\n'.join(perception_vals)
            errors += '\n\n\n'

        if errors:
            self.write({'notes': errors})
            form_res = self.env.ref('l10n_ar_eynes.view_create_arciba_nc_file')
            form_id = form_res and form_res.id or False
            res = {
                'name': _('Arciba'),
                'view_type': 'form',
                'view_mode': 'form',
                'views': [
                    (form_id, 'form'),
                ],
                'res_model': 'create.arciba.nc.file',
                'res_id': self.id,
                'view_id': form_id,
                'type': 'ir.actions.act_window',
                'target': 'new',
            }
        else:
            if perception_vals:
                res = self.generate_fw_file(perception_vals)
            else:
                raise ValidationError(
                    _(
                        "No perceptions/retentions from %(start)s to %(end)s to inform eArciba.",
                        start=self.period_start,
                        end=self.period_end,
                    )
                )
        return res
