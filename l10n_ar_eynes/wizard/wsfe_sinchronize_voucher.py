##############################################################################
#   Copyright (c) 2018 Eynes/E-MIPS (www.eynes.com.ar)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
##############################################################################

import json
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

    def _get_def_config(self):
        wsfe_conf_model = self.env['wsfe.config'].with_context(
            company_id=self.env.user.company_id.id
        )
        return wsfe_conf_model.get_config()

    voucher_type = fields.Many2one(
        'res.voucher.type', 'Voucher Type', required=True
    )
    pos_id = fields.Many2one('account.journal', 'POS', required=True)
    pos_id_domain = fields.Char(compute='_compute_pos_id_domain')
    config_id = fields.Many2one(
        'wsfe.config', 'Config', default=_get_def_config
    )
    voucher_number = fields.Integer('Number', required=True)
    document_type = fields.Many2one(
        'res.document.type', 'Document Type', readonly=True
    )
    document_number = fields.Char('Document Number', readonly=True)
    date_invoice = fields.Date('Date Invoice', readonly=False)
    amount_total = fields.Float(digits='Account', string="Total", readonly=True)
    amount_no_taxed = fields.Float(
        digits='Account', string="No Taxed", readonly=True
    )
    amount_taxed = fields.Float(digits='Account', string="Taxed", readonly=True)
    amount_tax = fields.Float(digits='Account', string="Tax", readonly=True)
    amount_exempt = fields.Float(
        digits='Account', string="Amount Exempt", readonly=True
    )
    cae = fields.Char('CAE', size=32, required=False, readonly=False)
    cae_due_date = fields.Date('CAE Due Date', readonly=False)
    date_process = fields.Datetime('Date Processed', readonly=True)
    infook = fields.Boolean('Info OK', default=False)
    invoice_id = fields.Many2one('account.move', 'Invoice')

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

    @api.onchange('voucher_number')
    def change_voucher_number(self):
        invoice_model = self.env['account.move']

        voucher_type = self.voucher_type.afip_code
        pos = int(self.pos_id.code)
        number = self.voucher_number

        if not voucher_type or not pos or not number:
            return

        res = self.config_id.get_voucher_info(pos, voucher_type, number)

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
        self.document_type = document_type
        self.document_number = str(res['DocNro'])
        self.date_invoice = di  # str(res['CbteFch']),
        self.amount_total = res['ImpTotal']
        self.amount_no_taxed = res['ImpTotConc']
        self.amount_taxed = res['ImpNeto']
        self.amount_tax = res['ImpIVA'] + res['ImpTrib']
        self.amount_exempt = res['ImpOpEx']
        self.cae = str(res['CodAutorizacion'])
        self.cae_due_date = dd
        self.date_process = dpr
        self.infook = True

        if self.document_number == '0':
            doc_number = [False, '0', '']
        else:
            doc_number = [self.document_number]

        if invoice_model.search([('cae', '=', self.cae)]):
            raise UserError(_('The voucher is already related to an invoice'))

        domain = [
            ('amount_total', '=', self.amount_total),
            ('amount_exempt', '=', self.amount_exempt),
            ('amount_untaxed', '=', self.amount_taxed),
            ('state', '=', 'draft'),
        ]
        if document_type and document_type.afip_code != '99':
            domain.append(('partner_id.vat', 'in', doc_number))
        invoice_ids = invoice_model.search(domain)
        if len(invoice_ids) == 1:
            self.invoice_id = invoice_ids and invoice_ids[0]
        else:
            self.invoice_id = False

        return {'domain': {'invoice_id': domain}}

    def relate_invoice(self):

        # Obtenemos los datos puestos por el usuario
        invoice = self.invoice_id

        if not self.infook:
            raise UserError(
                _("WSFE Error!\n" "Sinchronize process is not correct!")
            )

        pos = int(self.pos_id.code)
        number = self.voucher_number
        date_invoice = self.date_invoice
        invoice.wsfe_relate_invoice(
            pos, number, date_invoice, self.cae, self.cae_due_date
        )

        return {'type': 'ir.actions.act_window_close'}
