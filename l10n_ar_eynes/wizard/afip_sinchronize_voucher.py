##############################################################################
#   Copyright (c) 2018 Eynes/E-MIPS (www.eynes.com.ar)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
##############################################################################

import json
import re
import time

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT, float_is_zero
from odoo.tools.misc import DEFAULT_SERVER_DATETIME_FORMAT


class AFIPSinchronizeVoucher(models.TransientModel):
    """
    This wizard is used to get information about a voucher
    informed to AFIP through WSFE or WSFEX
    """

    _name = "afip.sinchronize.voucher"
    _description = "AFIP Sinchronize Voucher"

    voucher_type = fields.Many2one(
        'res.voucher.type', 'Voucher Type', required=True
    )
    pos_id = fields.Many2one('account.journal', 'POS', required=True)
    pos_id_domain = fields.Char(compute='_compute_pos_id_domain')
    wsfe_config_id = fields.Many2one('wsfe.config', 'Config')
    wsfex_config_id = fields.Many2one('wsfex.config', 'Config')
    voucher_number = fields.Integer('Number', required=True)

    document_type = fields.Many2one(
        'res.document.type',
        'Document Type',
        readonly=True,
        compute='_compute_sync_values',
    )
    document_number = fields.Char(
        'Document Number', readonly=True, compute='_compute_sync_values'
    )
    date_invoice = fields.Date(
        'Date Invoice', readonly=False, compute='_compute_sync_values'
    )
    amount_total = fields.Float(
        digits='Account',
        string="Total",
        readonly=True,
        compute='_compute_sync_values',
    )
    amount_no_taxed = fields.Float(
        digits='Account',
        string="No Taxed",
        readonly=True,
        compute='_compute_sync_values',
    )
    amount_taxed = fields.Float(
        digits='Account',
        string="Taxed",
        readonly=True,
        compute='_compute_sync_values',
    )
    amount_tax = fields.Float(
        digits='Account',
        string="Tax",
        readonly=True,
        compute='_compute_sync_values',
    )
    amount_exempt = fields.Float(
        digits='Account',
        string="Amount Exempt",
        readonly=True,
        compute='_compute_sync_values',
    )
    cae = fields.Char(
        'CAE',
        size=32,
        required=False,
        readonly=False,
        compute='_compute_sync_values',
    )
    cae_due_date = fields.Date(
        'CAE Due Date', readonly=False, compute='_compute_sync_values'
    )
    date_process = fields.Datetime(
        'Date Processed', readonly=True, compute='_compute_sync_values'
    )
    infook = fields.Boolean(
        'Info OK', default=False, compute='_compute_sync_values'
    )
    invoice_id = fields.Many2one('account.move', 'Invoice')
    error_msg = fields.Text(compute='_compute_sync_values')

    @api.model
    def default_get(self, fields):
        defaults = super(AFIPSinchronizeVoucher, self).default_get(fields)

        invoice_id = self.env.context.get('active_id')
        active_invoice = self.env['account.move'].browse(invoice_id)
        defaults.update(
            {
                'invoice_id': invoice_id,
                'wsfex_config_id': False,
                'wsfe_config_id': False,
                'voucher_type': active_invoice.voucher_type_id.id,
            }
        )
        if active_invoice.local:
            defaults.update(
                {
                    'wsfe_config_id': self.env['wsfe.config']
                    .with_context(company_id=self.env.company.id)
                    .get_config(),
                }
            )
        else:
            defaults.update(
                {
                    'wsfex_config_id': self.env['wsfex.config']
                    .with_context(company_id=self.env.company.id)
                    .get_config(),
                }
            )

        return defaults

    @api.depends('wsfe_config_id', 'wsfex_config_id', 'voucher_type')
    def _compute_pos_id_domain(self):
        for rec in self:
            ws_conf = rec.wsfe_config_id or rec.wsfex_config_id
            ids = [p.id for p in ws_conf.point_of_sale_ids.mapped('journal_id')]
            domain = [
                ('id', 'in', ids),
                ('denomination', '=', rec.voucher_type.denomination),
            ]
            rec.pos_id_domain = json.dumps(domain)

    def _clean_values(self):
        self.document_type = False
        self.document_number = ''
        self.date_invoice = False
        self.amount_total = 0.0
        self.amount_no_taxed = 0.0
        self.amount_taxed = 0.0
        self.amount_tax = 0.0
        self.amount_exempt = 0.0
        self.cae = ''
        self.cae_due_date = False
        self.date_process = False
        self.infook = False
        self.error_msg = ''

    @api.depends('voucher_number', 'pos_id', 'voucher_type')
    def _compute_sync_values(self):
        for rec in self:
            rec._clean_values()
            if rec.voucher_type and rec.pos_id and rec.voucher_number:
                ws_conf = rec.wsfe_config_id or rec.wsfex_config_id
                ws_pos = ws_conf.point_of_sale_ids.filtered(
                    lambda pos: pos.journal_id == self.pos_id
                )
                pos = int(ws_pos.code)

                rec.error_msg = rec._check_invoice_number_not_posted(
                    pos, rec.voucher_number
                )

                webservice = rec.wsfe_config_id or rec.wsfex_config_id

                try:
                    res = webservice.get_voucher_info(
                        pos, rec.voucher_type.afip_code, rec.voucher_number
                    )
                except Exception as e:
                    rec._clean_values()
                    rec.error_msg = str(e)
                else:
                    doc_ids = self.env['res.document.type'].search(
                        [('afip_code', '=', res['DocTipo'])]
                    )
                    document_type = doc_ids and doc_ids[0] or False

                    di = time.strftime(
                        DEFAULT_SERVER_DATE_FORMAT,
                        time.strptime(str(res['CbteFch']), '%Y%m%d'),
                    )
                    dd = time.strftime(
                        DEFAULT_SERVER_DATE_FORMAT,
                        time.strptime(str(res['FchVto']), '%Y%m%d'),
                    )
                    dpr = False
                    if res['FchProceso']:
                        dpr = time.strftime(
                            DEFAULT_SERVER_DATETIME_FORMAT,
                            time.strptime(
                                str(res['FchProceso']), '%Y%m%d%H%M%S'
                            ),
                        )

                    rec.document_type = document_type
                    rec.document_number = str(res['DocNro'])
                    rec.date_invoice = di
                    rec.amount_total = float(res['ImpTotal'])
                    rec.amount_no_taxed = res.get('ImpTotConc', 0)
                    rec.amount_taxed = res.get('ImpNeto', 0)
                    rec.amount_tax = float(res.get('ImpIVA', 0)) + float(
                        res.get('ImpTrib', 0)
                    )
                    rec.amount_exempt = res.get('ImpOpEx', 0)
                    rec.cae = str(res['CodAutorizacion'])
                    rec.cae_due_date = dd
                    rec.date_process = dpr
                    rec.infook = True

                    domain = [
                        ('move_type', 'in', ('out_invoice', 'out_refund')),
                        ('state', '=', 'draft'),
                    ]
                    if (
                        rec.invoice_id.local
                        and rec.document_type
                        and not (rec.document_type.afip_code in ['99', '96'])
                    ):
                        if rec.document_number == '0':
                            doc_number = [False, '0', '']
                        else:
                            doc_number = [rec.document_number]
                        domain.append(('partner_id.vat', 'in', doc_number))
                    invoice_ids = self.env['account.move'].search(domain)
                    invoice_ids = invoice_ids.filtered(
                        lambda inv: float_is_zero(
                            inv.amount_total - rec.amount_total,
                            precision_rounding=inv.currency_id.rounding,
                        )
                    )
                    if rec.invoice_id not in invoice_ids:
                        rec.error_msg = _(
                            "The selected invoice doesn't match with the AFIP data obtained."
                        )

    def _check_invoice_number_not_posted(self, pos, number):
        voucher_number = '%05d-%08d' % (pos, number)
        invoices_same_type = self.env['account.move'].search(
            [
                ('voucher_type_id', '=', self.voucher_type.id),
                ('state', '=', 'posted'),
                ('name', 'ilike', voucher_number),
            ]
        )
        if invoices_same_type:
            return _(
                "The selected voucher number is already related to a posted invoice."
            )
        return ''

    def relate_invoice(self):
        if (not self.infook or not self.invoice_id) or self.error_msg:
            raise UserError(
                _("WSFE Error!\n" "Sinchronize process is not correct!")
            )

        invoice = self.invoice_id
        pos = self.pos_id.code
        if pos:
            pos = int(re.sub("[^0-9]", "", pos))
        number = self.voucher_number
        date_invoice = self.date_invoice
        invoice.wsfe_relate_invoice(
            pos,
            number,
            self.voucher_type,
            date_invoice,
            self.cae,
            self.cae_due_date,
        )

        return {'type': 'ir.actions.act_window_close'}
