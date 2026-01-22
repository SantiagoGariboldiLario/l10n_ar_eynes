import binascii
import codecs
import json
import logging
import re
import tempfile
from datetime import datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT

logger = logging.getLogger(__name__)


class CreateIVARetentionFile(models.TransientModel):
    _name = 'create.iva.retention.file'
    _description = 'Create Iva Retention File'

    company_id = fields.Many2one('res.company', required=True)
    company_id_domain = fields.Char(
        default=lambda self: self._default_company_ids()
    )
    date_start = fields.Date(required=True)
    date_stop = fields.Date(required=True)
    notes = fields.Char('Notes')

    @api.model
    def _default_company_ids(self):
        return json.dumps(
            [('id', 'in', self.env.context.get('allowed_company_ids', []))]
        )

    def create_retention_file(self):
        retention_query = """
        SELECT r.id FROM account_payment_order_retention_line r
        -- JOIN account_journal ret ON r.retention_id = ret.id
        -- JOIN account_tax at ON ret.tax_id=at.id
        JOIN account_tax at ON r.retention_id = at.id
        JOIN account_payment_order apo ON r.payment_order_id = apo.id
        WHERE r.date BETWEEN %(date_start)s
        AND %(date_stop)s
        AND at.retention_type  = 'vat'
        AND at.type_tax_use LIKE 'sale'
        AND r.company_id = %(company_id)s
        AND apo.state = 'posted'
        ORDER BY r.date
        """

        cr = self._cr
        cr.execute(
            retention_query,
            {
                'date_start': self.date_start,
                'date_stop': self.date_stop,
                'company_id': self.company_id.id,
            },
        )
        res = cr.fetchall()
        if not len(res):
            raise UserError(
                _(
                    'Export Error\n'
                    'Applicable Retentions for export not found. \n'
                    'HINT: Is there any IVA retentions supported for this period?'
                )
            )
        retention_ids = [retention_ids[0] for retention_ids in res]

        retention_errors = self._generate_retention_file(retention_ids)

        errors = ''
        if retention_errors:
            errors += _('Retention File Errors\n================\n')
            errors += '\n'.join(retention_errors)

        if errors:
            self.write({'notes': errors})
            form_id = self.env.ref(
                'l10n_ar_eynes.view_create_iva_retention_file'
            ).id
            res = {
                'name': _('IVA Retention Supported File Generation'),
                'view_type': 'form',
                'view_mode': 'form',
                'views': [
                    (form_id, 'form'),
                ],
                'res_model': 'create.iva.retention.file',
                'res_id': self.id,
                'view_id': form_id,
                'type': 'ir.actions.act_window',
                'target': 'new',
            }
        else:
            res = True

        return res

    def _get_period_name(self):
        period_start = datetime.strptime(
            str(self.date_start), DEFAULT_SERVER_DATE_FORMAT
        )
        return "%s-%s" % (period_start.month, period_start.year)

    def _generate_retention_file(self, retention_ids):
        head_file_errors = []
        head_regs = []

        tax_lines = self.env['account.payment.order.retention.line'].browse(
            retention_ids
        )

        journal_afip_code_map = {
            journal.tax_id.id: journal.afip_code
            for journal in self.env['account.journal'].search(
                [
                    ('tax_id', 'in', tax_lines.mapped('retention_id').ids),
                    ('afip_code', '!=', False),
                ]
            )
        }

        for tax_line in tax_lines:

            tax_line_name = tax_line.get_readeable_name()

            date = str(tax_line.date)

            nro_doc_retenido = tax_line.partner_id.vat
            if not nro_doc_retenido:
                head_file_errors.append(
                    _('%s: Partner VAT not found\n') % (tax_line_name,)
                )

            reg_code = (
                tax_line.concept_id.code
            )  # TODO: DOCUMENTAR, reg.code para soportadas esta en el concepto
            if not reg_code:
                reg_code = 0
                head_file_errors.append(
                    _('%s: Reg.code not found\n') % (tax_line_name,)
                )

            # afip_code = tax_line.retention_id.afip_code
            afip_code = journal_afip_code_map.get(tax_line.retention_id.id)
            if not afip_code:
                afip_code = 0
                head_file_errors.append(
                    _('%s: AFIP retention code not found\n') % (tax_line_name,)
                )

            num_cert = ""
            if tax_line.certificate_no:
                num_cert = str(tax_line.certificate_no)

            asocciated_invoice = tax_line.payment_order_id.income_line_ids[
                0
            ].move_line_id.move_id

            pattern = re.compile(r'(FCE|NCE|NDE)')
            inv_name = asocciated_invoice.name
            match = pattern.search(inv_name)
            if match:
                inv_name = inv_name.replace(match.group(), '')

            line = [
                str(afip_code),
                str(reg_code),
                nro_doc_retenido.replace('-', ''),
                '',  # Corresponde informar la CUIT Intermediario cuando es un contribuyente cesionario.
                date,
                asocciated_invoice.voucher_type_id.afip_code,
                inv_name,
                num_cert,
                str(tax_line.amount).replace('.', ','),
            ]
            head_regs.append(line)

        # Chequeamos si hubo errores
        if len(head_file_errors):
            logger.info(head_file_errors)
            return head_file_errors

        head_filename = tempfile.mkstemp(suffix='.iva')[1]
        f = codecs.open(head_filename, "w", "utf-8")

        for r in head_regs:
            try:
                f.write(';'.join(r))
            except Exception as e:
                raise e
            f.write('\r\n')

        f.close()
        f = open(head_filename, 'r')

        name = 'IVA_RET_SUP_%s.csv' % self._get_period_name()
        generated_file_rec = self.env['iva.ret.generated.files'].create(
            {
                'code': name,
                'date_from': self.date_start,
                'date_to': self.date_stop,
                'company_id': self.company_id.id,
            }
        )

        data_attach = {
            'name': name,
            'datas': binascii.b2a_base64(f.read().encode('utf-8')),
            # 'datas_fname': name,
            'res_model': 'iva.ret.generated.files',
            'res_id': generated_file_rec.id,
        }
        doc = self.env['ir.attachment'].create(data_attach)
        generated_file_rec.write({'attachment_id': doc.id})
        f.close()

        return []


class CreateIVAPerceptionFile(models.TransientModel):
    _name = 'create.iva.perception.file'
    _description = 'Create Iva Perception File'

    company_id = fields.Many2one('res.company', required=True)
    company_id_domain = fields.Char(
        default=lambda self: self._default_company_ids()
    )
    date_start = fields.Date(required=True)
    date_stop = fields.Date(required=True)
    notes = fields.Char('Notes')

    @api.model
    def _default_company_ids(self):
        return json.dumps(
            [('id', 'in', self.env.context.get('allowed_company_ids', []))]
        )

    def create_perception_file(self):
        retention_query = """
            SELECT p.id
            FROM perception_tax_line p
            JOIN account_move i ON p.invoice_id = i.id
            -- JOIN account_journal per ON p.perception_id = per.id
            -- JOIN account_tax at ON per.tax_id=at.id
            JOIN account_tax at ON p.perception_id = at.id
            WHERE p.date BETWEEN %(date_start)s AND %(date_stop)s
            AND p.company_id = %(company_id)s
            AND at.retention_type = 'vat'
            AND at.type_tax_use LIKE 'purchase'  -- Only perceptions suffered
            AND i.state = 'posted'
            ORDER BY p.date """

        cr = self._cr
        cr.execute(
            retention_query,
            {
                'date_start': self.date_start,
                'date_stop': self.date_stop,
                'company_id': self.company_id.id,
            },
        )
        res = cr.fetchall()
        if not len(res):
            raise UserError(
                _(
                    'Export Error\n'
                    'Applicable perceptions for export not found. \n'
                    'HINT: Is there any IVA perceptions supported for this period?'
                )
            )
        perception_ids = [perception_ids[0] for perception_ids in res]

        perception_errors = self._generate_perception_file(perception_ids)

        errors = ''
        if perception_errors:
            errors += _('Perception File Errors\n================\n')
            errors += '\n'.join(perception_errors)

        if errors:
            self.write({'notes': errors})
            form_id = self.env.ref(
                'l10n_ar_eynes.view_create_iva_perception_file'
            ).id
            res = {
                'name': _('IVA Perception Supported File Generation'),
                'view_type': 'form',
                'view_mode': 'form',
                'views': [
                    (form_id, 'form'),
                ],
                'res_model': 'create.iva.perception.file',
                'res_id': self.id,
                'view_id': form_id,
                'type': 'ir.actions.act_window',
                'target': 'new',
            }
        else:
            res = True

        return res

    def _get_period_name(self):
        period_start = datetime.strptime(
            str(self.date_start), DEFAULT_SERVER_DATE_FORMAT
        )
        return "%s-%s" % (period_start.month, period_start.year)

    def _generate_perception_file(self, perception_ids):
        head_file_errors = []
        head_regs = []
        for tax_line in self.env['perception.tax.line'].browse(perception_ids):
            date = str(tax_line.date)

            tax_line_name = tax_line.get_readeable_name()

            nro_doc_retenido = tax_line.partner_id.vat
            if not nro_doc_retenido:
                head_file_errors.append(
                    _('%s: Partner VAT not found\n') % (tax_line_name,)
                )

            reg_code = tax_line.concept_id.code
            if not reg_code:
                reg_code = 0
                logger.info(('%s: Reg.code not found\n') % (tax_line_name,))

            invoice = tax_line.invoice_id

            line = [
                str(reg_code),
                nro_doc_retenido.replace('-', ''),
                '',  # Corresponde informar la CUIT Intermediario cuando es un contribuyente cesionario.
                date,
                invoice.voucher_type_id.afip_code,
                invoice.supplier_move_reference,
                str(tax_line.amount).replace('.', ','),
            ]
            head_regs.append(line)

        # Chequeamos si hubo errores
        if len(head_file_errors):
            logger.info(head_file_errors)
            return head_file_errors

        head_filename = tempfile.mkstemp(suffix='.iva')[1]
        f = codecs.open(head_filename, "w", "utf-8")

        for r in head_regs:
            try:
                f.write(';'.join(r))
            except Exception as e:
                raise e
            f.write('\r\n')

        f.close()

        f = open(head_filename, 'r')

        name = 'IVA_PER_SUP_%s.csv' % self._get_period_name()
        generated_file_rec = self.env['iva.per.generated.files'].create(
            {
                'code': name,
                'date_from': self.date_start,
                'date_to': self.date_stop,
                'company_id': self.company_id.id,
            }
        )

        data_attach = {
            'name': name,
            'datas': binascii.b2a_base64(f.read().encode('utf-8')),
            # 'datas_fname': name,
            'res_model': 'iva.per.generated.files',
            'res_id': generated_file_rec.id,
        }
        doc = self.env['ir.attachment'].create(data_attach)
        generated_file_rec.write({'attachment_id': doc.id})
        f.close()

        return []
