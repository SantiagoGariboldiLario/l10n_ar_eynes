##############################################################################
#   Copyright (c) 2019 Eynes/E-MIPS (www.eynes.com.ar)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
##############################################################################

import logging
import re
from datetime import datetime
from decimal import Decimal

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT

from ..utils.sicore_fixed_width import FixedWidth, moneyfmt
from ..utils.sifere_fixed_width_dicts import HEAD_LINES_PER, HEAD_LINES_RET

logger = logging.getLogger(__name__)

vn_regex_pattern = r'[\s\D-]'


class CreateSifereFiles(models.TransientModel):
    _name = 'create.sifere.files'
    _desc = 'Create SIFERE Files'

    period_start = fields.Date('Date start')
    period_end = fields.Date('Date end')

    @api.constrains('period_start', 'period_end')
    def _check_period(self):
        for rec in self:
            period_start = datetime.strptime(
                str(rec.period_start), DEFAULT_SERVER_DATE_FORMAT
            )
            period_end = datetime.strptime(
                str(rec.period_end), DEFAULT_SERVER_DATE_FORMAT
            )

            if period_start.year != period_end.year:
                raise ValidationError(
                    _("Date start and date end must be in the same month")
                )

            if period_start.month != period_end.month:
                raise ValidationError(
                    _("Date start and date end must be in the same month")
                )

    def _get_period_name(self):
        period_start = datetime.strptime(
            str(self.period_start), DEFAULT_SERVER_DATE_FORMAT
        )
        return "%s-%s" % (period_start.month, period_start.year)

    def create_files(self):
        exporters = self.env['report.exporter'].search(
            [('codename', 'ilike', '%%sifere%%')]
        )
        generator_obj = self.env['report.files.generator']
        result = _("SIFERE - Generated reports details - Period %s\n") % (
            self._get_period_name()
        )
        for exp in exporters:
            vals = {
                'date_start': self.period_start,
                'date_stop': self.period_end,
                'exporter_id': exp.id,
            }
            rfe = generator_obj.create(vals)
            fname = '_do_%s' % exp.codename
            if not hasattr(rfe, fname):
                raise ValidationError(
                    _('Exporter Failure.\n[undefined %s]') % fname
                )
            fn = getattr(rfe, fname)
            try:
                res = fn()
            except Exception as e:
                result += _(
                    "%(name)s - Could not generate report - %(err)s\n",
                    name=exp.name,
                    err=str(e),
                )
                continue

            try:
                # report_exist = self.env['report.files'].search([
                #   ('exporter_codename', '=', exp.codename),
                #   ('period_id', '=', self.period_id.id)
                # ])
                # if report_exist:
                #     report_exist.regenerate()
                #     result += _(
                # "%s - Report already existed, was regenerated successfully.\n"
                # ) % (exp.name)
                # else:
                end_res = rfe.postprocess(res)
                if not end_res or len(res['errors']) > 0:
                    result += _(
                        "%s - Report generated with errors, "
                        "check the report for more details.\n"
                    ) % (exp.name)
                else:
                    result += _("%s - The file was created successfully.\n") % (
                        exp.name
                    )
            except Exception as e:
                result += ("%s - %s\n") % (exp.name, str(e))

        context = dict(self._context or {})
        context["message"] = result
        view = self.env.ref("popup_messages.message_wizard")
        view_id = view and view.id or False

        return {
            'name': _('SIFERE - Create Files'),
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'message.wizard',
            'views': [(view_id, 'form')],
            'view_id': view_id,
            'target': 'new',
            'context': context,
        }


class ReportFilesGenerator(models.Model):
    _inherit = 'report.files.generator'

    def _get_period_name(self):
        date_start = datetime.strptime(
            str(self.date_start), DEFAULT_SERVER_DATE_FORMAT
        )
        return "%s-%s" % (date_start.month, date_start.year)

    def _do_sifere(self, method):
        data = getattr(self, method)()
        errors = data.get('errors')
        files = data.get('files')
        state = not bool(errors)

        ddict = {
            'state': state,
            'errors': errors,
            'files': files,
        }
        return ddict

    def _do_sifere_ret(self):
        return self._do_sifere('create_retention_file')

    def create_retention_file(self):
        company_id = self.env.user.company_id.id
        cr = self._cr

        retention_query = """
        SELECT r.id FROM account_payment_order_retention_line r
        JOIN account_journal ret ON r.retention_id = ret.id
        JOIN account_tax at ON ret.tax_id=at.id
        WHERE r.date BETWEEN %(date_from)s AND %(date_to)s
        AND ret.type in ('gross_income') AND at.type_tax_use LIKE 'sale'
        AND r.company_id = %(company_id)s ORDER BY r.date
        """

        cr.execute(
            retention_query,
            {
                'date_from': self.date_start,
                'date_to': self.date_stop,
                'company_id': company_id,
            },
        )
        res = cr.fetchall()

        if not len(res):
            raise Exception(
                _("No retentions have been found with the selected values")
            )

        retention_ids = [retention_ids[0] for retention_ids in res]

        perception_query = """
        SELECT p.id FROM perception_tax_line p
        JOIN account_journal per ON p.perception_id = per.id
        JOIN account_tax at ON per.tax_id=at.id
        JOIN account_move i ON p.invoice_id=i.id
        WHERE p.date BETWEEN %(date_from)s AND %(date_to)s
        AND i.state IN %(inv_state)s
        AND per.type in %(type)s AND at.type_tax_use LIKE 'purchase'
        AND p.company_id = %(company_id)s
        AND at.is_bank_settlement IS True
        ORDER BY p.date
        """

        q_data_perception = {
            'date_from': self.date_start,
            'date_to': self.date_stop,
            'type': ('gross_income',),
            'inv_state': (
                'open',
                'paid',
            ),
            'company_id': company_id,
        }
        cr.execute(perception_query, q_data_perception)
        perception_res = cr.fetchall()
        perception_ids = []
        if len(perception_res):
            perception_ids = [
                perception_ids[0] for perception_ids in perception_res
            ]

        res = self._generate_retention_file(retention_ids, perception_ids)
        return res

    @api.model
    def _generate_retention_file(self, retention_ids, perception_ids):
        retention_tax_line_obj = self.env[
            'account.payment.order.retention.line'
        ]
        sifere_jurisdiction_obj = self.env['sifere.jurisdiction']
        sifere_config = self.env['sifere.config'].search(
            [('name', '=', 'Default')]
        )
        fixed_width = FixedWidth(HEAD_LINES_RET)

        regs = []
        errors = []
        for tax_line in retention_tax_line_obj.browse(retention_ids):
            # String(YYYY-MM-DD)->Datetime
            date = datetime.strptime(str(tax_line.date), '%Y-%m-%d')
            # Datetime->String: dd/mm/yyyy
            date = datetime.strftime(date, '%d/%m/%Y')
            tax_line_name = tax_line.get_readeable_name()
            logger.info('Processing %s' % tax_line_name)
            nro_doc_retenido = tax_line.partner_id.vat
            if not nro_doc_retenido:
                errors.append(
                    {
                        'error': _('Partner VAT not found'),
                        'resource': tax_line.partner_id,
                    }
                )
            if '-' not in nro_doc_retenido and len(nro_doc_retenido) == 11:
                nro_doc_retenido = '{}-{}-{}'.format(
                    nro_doc_retenido[0:2],
                    nro_doc_retenido[2:10],
                    nro_doc_retenido[10],
                )
            jurisdiction = sifere_jurisdiction_obj.search(
                [('state', '=', tax_line.retention_id.state_id.id)]
            )
            if not jurisdiction.code:
                jurisdiction_code = 0
                if not sifere_config.ignore_jurisdiction:
                    errors.append(
                        {
                            'error': _('Jurisdiction cannot be found'),
                            'resource': tax_line.retention_id,
                        }
                    )
            else:
                jurisdiction_code = jurisdiction.code

            number = tax_line.payment_order_id.number
            num_voucher = re.sub(vn_regex_pattern, '', number)
            num_constancia = re.sub(r'-', '0', tax_line.certificate_no or '')
            line = {
                'codigo_jurisdiccion': jurisdiction_code,
                'cuit': nro_doc_retenido,
                'fecha_retencion': date,
                'numero_sucursal': num_voucher[:4],
                'numero_constancia': num_constancia,
                'tipo_comprobante': 'O',
                'letra_comprobante': '',
                'num_comprobante_original': num_voucher,
                'monto_retencion': moneyfmt(
                    Decimal(tax_line.amount), places=2, ndigits=8, dp=','
                ),
            }

            # Apendeamos el registro
            fixed_width.update(**line)
            regs.append(fixed_width.line)

        # Percepciones de Liquidacion Bancaria
        perception_tax_line_obj = self.env['perception.tax.line']
        for tax_line in perception_tax_line_obj.browse(perception_ids):
            # String(YYYY-MM-DD)->Datetime
            date = datetime.strptime(str(tax_line.date), '%Y-%m-%d')
            # Datetime->String: dd/mm/yyyy
            date = datetime.strftime(date, '%d/%m/%Y')
            tax_line_name = tax_line.get_readeable_name()
            logger.info('Processing %s' % tax_line_name)
            nro_doc_percibido = tax_line.partner_id.vat
            if not nro_doc_percibido:
                errors.append(
                    {
                        'error': _('Partner VAT not found'),
                        'resource': tax_line.partner_id,
                    }
                )
            if '-' not in nro_doc_percibido and len(nro_doc_percibido) == 11:
                nro_doc_percibido = '{}-{}-{}'.format(
                    nro_doc_percibido[0:2],
                    nro_doc_percibido[2:10],
                    nro_doc_percibido[10],
                )
            jurisdiction = sifere_jurisdiction_obj.search(
                [('state', '=', tax_line.perception_id.state_id.id)]
            )
            if not jurisdiction.code:
                jurisdiction_code = 0
                if not sifere_config.ignore_jurisdiction:
                    errors.append(
                        {
                            'error': _('Jurisdiction cannot be found'),
                            'resource': tax_line.perception_id,
                        }
                    )
            else:
                jurisdiction_code = jurisdiction.code

            internal_number_split = tax_line.invoice_id.internal_number.split(
                '-'
            )
            tipo_cbte = self._get_tipo_comprobante(tax_line.invoice_id)
            if tipo_cbte == 'C':
                sign = -1
            else:
                sign = 1
            line = {
                'codigo_jurisdiccion': jurisdiction_code,
                'cuit': nro_doc_percibido,
                'fecha_retencion': date,
                'numero_sucursal': internal_number_split[0],
                'numero_constancia': internal_number_split[1],
                'tipo_comprobante': 'O',
                'letra_comprobante': '',
                'monto_retencion': moneyfmt(
                    Decimal(tax_line.amount) * sign, places=2, ndigits=9, dp=','
                ),
            }

            # Apendeamos el registro
            fixed_width.update(**line)
            regs.append(fixed_width.line)

        name = 'SIFERE_RET_%s.txt' % self._get_period_name()

        data = {
            'errors': errors,
            'files': [
                {
                    'name': name,
                    'data': regs,
                }
            ],
        }
        return data

    def _do_sifere_per(self):
        return self._do_sifere('create_perception_file')

    def create_perception_file(self):
        company_id = self.env.user.company_id.id
        cr = self._cr

        perception_query = """
        SELECT p.id FROM perception_tax_line p
        JOIN account_journal per ON p.perception_id = per.id
        JOIN account_tax at ON per.tax_id=at.id
        JOIN account_move i ON p.invoice_id=i.id
        WHERE p.date BETWEEN %(date_from)s AND %(date_to)s
        AND i.state IN %(inv_state)s
        AND per.type in %(type)s AND at.type_tax_use LIKE 'purchase'
        AND p.company_id = %(company_id)s
        AND at.is_bank_settlement IS NOT True
        ORDER BY p.date
        """

        q_data = {
            'date_from': self.date_start,
            'date_to': self.date_stop,
            'type': ('gross_income',),
            'inv_state': (
                'open',
                'paid',
            ),
            'company_id': company_id,
        }
        cr.execute(perception_query, q_data)
        res = cr.fetchall()

        if not len(res):
            raise Exception(
                _("No perceptions have been found with the selected values")
            )

        perception_ids = [perception_ids[0] for perception_ids in res]

        res = self._generate_perception_file(perception_ids)
        return res

    @api.model
    def _get_tipo_comprobante(self, invoice_id):
        res = None
        if invoice_id.type == 'in_invoice':
            if invoice_id.is_debit_note:
                res = 'D'
            else:
                res = 'F'
        elif invoice_id.type == 'in_refund':
            res = 'C'
        return res

    @api.model
    def _generate_perception_file(self, perception_ids):
        perception_tax_line_obj = self.env['perception.tax.line']
        sifere_jurisdiction_obj = self.env['sifere.jurisdiction']
        sifere_config = self.env['sifere.config'].search(
            [('name', '=', 'Default')]
        )
        fixed_width = FixedWidth(HEAD_LINES_PER)

        regs = []
        errors = []
        for tax_line in perception_tax_line_obj.browse(perception_ids):
            # String(YYYY-MM-DD)->Datetime
            date = datetime.strptime(str(tax_line.date), '%Y-%m-%d')
            # Datetime->String: dd/mm/yyyy
            date = datetime.strftime(date, '%d/%m/%Y')
            tax_line_name = tax_line.get_readeable_name()
            logger.info('Processing %s' % tax_line_name)
            nro_doc_percibido = tax_line.partner_id.vat
            if not nro_doc_percibido:
                errors.append(
                    {
                        'error': _('Partner VAT not found'),
                        'resource': tax_line.partner_id,
                    }
                )
            if '-' not in nro_doc_percibido and len(nro_doc_percibido) == 11:
                nro_doc_percibido = '{}-{}-{}'.format(
                    nro_doc_percibido[0:2],
                    nro_doc_percibido[2:10],
                    nro_doc_percibido[10],
                )
            jurisdiction = sifere_jurisdiction_obj.search(
                [('state', '=', tax_line.perception_id.state_id.id)]
            )
            if not jurisdiction.code:
                jurisdiction_code = 0
                if not sifere_config.ignore_jurisdiction:
                    errors.append(
                        {
                            'error': _('Jurisdiction cannot be found'),
                            'resource': tax_line.perception_id,
                        }
                    )
            else:
                jurisdiction_code = jurisdiction.code

            internal_number_split = tax_line.invoice_id.internal_number.split(
                '-'
            )
            tipo_cbte = self._get_tipo_comprobante(tax_line.invoice_id)
            if tipo_cbte == 'C':
                sign = -1
            else:
                sign = 1
            line = {
                'codigo_jurisdiccion': jurisdiction_code,
                'cuit': nro_doc_percibido,
                'fecha_percepcion': date,
                'numero_sucursal': internal_number_split[0],
                'numero_constancia': internal_number_split[1],
                'tipo_comprobante': tipo_cbte,
                'letra_comprobante': tax_line.invoice_id.denomination or '',
                'monto_percepcion': moneyfmt(
                    Decimal(tax_line.amount) * sign, places=2, ndigits=9, dp=','
                ),
            }

            # Apendeamos el registro
            fixed_width.update(**line)
            regs.append(fixed_width.line)

        name = 'SIFERE_PER_%s.txt' % self._get_period_name()

        data = {
            'errors': errors,
            'files': [
                {
                    'name': name,
                    'data': regs,
                }
            ],
        }
        return data
