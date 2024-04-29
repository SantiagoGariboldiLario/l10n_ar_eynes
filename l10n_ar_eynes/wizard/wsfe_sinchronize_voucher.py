##############################################################################
#   Copyright (c) 2018 Eynes/E-MIPS (www.eynes.com.ar)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
##############################################################################

import json
import re
import time

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT
from odoo.tools.misc import DEFAULT_SERVER_DATETIME_FORMAT


class WsfeSinchronizeCoucher(models.TransientModel):
    """
    This wizard is used to get information about a voucher
    informed to AFIP through WSFE
    """

    _name = "wsfe.sinchronize.voucher"
    _description = "WSFE Sinchronize Voucher"

    voucher_type = fields.Many2one(
        'res.voucher.type', 'Voucher Type', required=True
    )
    pos_id = fields.Many2one('account.journal', 'POS', required=True)
    pos_id_domain = fields.Char(compute='_compute_pos_id_domain')
    config_id = fields.Many2one(
        'wsfe.config', 'Config', default=lambda self: self._get_def_config()
    )
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
    invoice_id_domain = fields.Char(compute='_compute_sync_values')
    invoice_id = fields.Many2one('account.move', 'Invoice')
    error_msg = fields.Text(compute='_compute_sync_values')

    def _get_def_config(self):
        wsfe_conf_model = self.env['wsfe.config'].with_context(
            company_id=self.env.user.company_id.id
        )
        return wsfe_conf_model.get_config()

    @api.depends('config_id', 'voucher_type')
    def _compute_pos_id_domain(self):
        for rec in self:
            wsfe_conf = rec.config_id
            ids = [
                p.id for p in wsfe_conf.point_of_sale_ids.mapped('journal_id')
            ]
            rec.voucher_type.denomination or False
            domain = [('id', 'in', ids)]
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
        self.invoice_id_domain = '[]'
        self.invoice_id = False
        self.error_msg = ''

    @api.depends('voucher_number', 'pos_id', 'voucher_type')
    def _compute_sync_values(self):
        for rec in self:
            if not rec.voucher_type or not rec.pos_id or not rec.voucher_number:
                rec._clean_values()
            else:
                pos = rec.pos_id.code
                if pos:
                    pos = int(re.sub("[^0-9]", "", pos))

                try:
                    res = rec.config_id.get_voucher_info(
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
                    dpr = time.strftime(
                        DEFAULT_SERVER_DATETIME_FORMAT,
                        time.strptime(str(res['FchProceso']), '%Y%m%d%H%M%S'),
                    )

                    # TODO: Tandriamos que filtrar las invoices por
                    # Tipo de Comprobante tambien para ello podemos agregar
                    # un par de campos mas para usarlos como filtros,
                    # por ejemplo, is_debit_note y type
                    rec.document_type = document_type
                    rec.document_number = str(res['DocNro'])
                    rec.date_invoice = di  # str(res['CbteFch']),
                    rec.amount_total = res['ImpTotal']
                    rec.amount_no_taxed = res['ImpTotConc']
                    rec.amount_taxed = res['ImpNeto']
                    rec.amount_tax = float(res['ImpIVA']) + float(
                        res['ImpTrib']
                    )
                    rec.amount_exempt = res['ImpOpEx']
                    rec.cae = str(res['CodAutorizacion'])
                    rec.cae_due_date = dd
                    rec.date_process = dpr
                    rec.infook = True
                    rec.error_msg = ''

                    if rec.document_number == '0':
                        doc_number = [False, '0', '']
                    else:
                        doc_number = [rec.document_number]

                    domain = [
                        ('amount_total', '=', rec.amount_total),
                        ('amount_exempt', '=', rec.amount_exempt),
                        ('amount_untaxed', '=', rec.amount_taxed),
                        ('state', '=', 'draft'),
                    ]
                    if document_type and not (
                        document_type.afip_code in ['99', '96']
                    ):
                        domain.append(('partner_id.vat', 'in', doc_number))
                    AccountMove = self.env['account.move']
                    invoice_ids = AccountMove.search(domain)
                    if AccountMove.search(
                        [
                            ('cae', '=', rec.cae),
                            ('id', 'not in', invoice_ids.ids),
                        ]
                    ):
                        raise UserError(
                            _('The voucher is already related to an invoice')
                        )

                    rec.invoice_id_domain = json.dumps(domain)

    def relate_invoice(self):
        if not self.infook or not self.invoice_id:
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
