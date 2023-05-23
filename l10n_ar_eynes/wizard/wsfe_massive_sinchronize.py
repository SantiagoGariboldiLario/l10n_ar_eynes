##############################################################################
#   Copyright (c) 2018 Eynes/E-MIPS (www.eynes.com.ar)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
##############################################################################

import logging
import time

from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT

logger = logging.getLogger(__name__)


class WsfeMassiveSinchronize(models.TransientModel):
    _name = 'wsfe.massive.sinchronize'
    _description = 'WSFE Massive Sinchronize'

    voucher_type = fields.Many2one(
        'res.voucher.type', 'Voucher Type', required=True
    )
    pos_id = fields.Many2one('account.journal', 'POS', required=True)

    def _search_invoice(self, res):
        invoice_model = self.env['account.move']

        amount_total = res['ImpTotal']
        amount_no_taxed = res['ImpTotConc']
        amount_taxed = res['ImpNeto']
        # amount_tax = res['ImpIVA'] + res['ImpTrib']
        amount_exempt = res['ImpOpEx']

        domain = [
            ('amount_total', '=', amount_total),
            ('amount_exempt', '=', amount_exempt),
            ('amount_taxed', '=', amount_taxed),
            ('amount_no_taxed', '=', amount_no_taxed),
            ('state', 'in', ('draft')),
            ('move_type', 'in', ('out_invoice', 'out_refund')),
        ]

        # TODO: Estamos repitiendo codigo. Limpiar.
        doc_ids = self.env['res.document.type'].search(
            [('afip_code', '=', res['DocTipo'])]
        )
        document_type = doc_ids and doc_ids[0] or False
        document_number = (
            [str(res['DocNro'])]
            if res['DocNro']
            else [str(res['DocNro']), '', False]
        )
        if document_type and document_type.afip_code != '99':
            domain.append(('partner_id.vat', 'in', document_number))

        invoices = invoice_model.search(domain)

        if len(invoices) == 1:
            return invoices
        # Si hay mas de una, retorna la primera que tenga wsfe_request
        if len(invoices) > 1:
            final_inv = invoices.filtered(lambda x: x.wsfe_request_ids)
            if final_inv:
                return final_inv[0]
        return False

    def sinchronize(self):
        self.ensure_one()
        wsfe_conf_model = self.env['wsfe.config']
        invoice_model = self.env['account.move']
        company = self.pos_id.company_id
        conf = wsfe_conf_model.with_context(company_id=company.id).get_config()
        pos = int(self.pos_id.get_pos_number())
        voucher_type = self.voucher_type.afip_code

        # Obtenemos el ultimo numero de factura
        # FIX: Corregir en el caso que sea una ND
        is_debit_note = False
        document_type = 'out_invoice'
        if self.voucher_type.doc_type == 'cn':
            document_type = 'out_refund'
        elif self.voucher_type.doc_type == 'dn':
            is_debit_note = True
        last_invoice = invoice_model.search(
            [
                ('state', 'in', ('open', 'paid')),
                ('journal_id', '=', self.pos_id.id),
                ('move_type', '=', document_type),
                ('is_debit_note', '=', is_debit_note),
                ('denomination', '=', self.voucher_type.denomination),
            ],
            order='name desc',
            limit=1,
        )

        # Buscamos la desincronizacion
        # Verificamos antes si existe o no una factura en el sistema
        if last_invoice:
            last_number = int(last_invoice.name.split('-')[1])
        else:
            last_invoice = 1
            last_wsfe_number = conf.get_last_voucher(pos, voucher_type)

            # Chequeamos si esta todo sincronizado
            if last_number == last_wsfe_number:
                raise UserError(
                    _('All voucher of this type and POS are sinchronized.')
                )

            invoices = self.env['account.move']
            for number in range(last_number + 1, last_wsfe_number + 1):
                logger.info("Sincronizando comprobante %d" % number)
                res = conf.get_voucher_info(pos, voucher_type, number)
                logger.debug("Informacion obtenida de AFIP %s" % res)

                # Buscamos una factura que coincida
                invoice = self._search_invoice(res)

                # No se encontro la factura
                if not invoice:
                    raise UserError(
                        _(
                            'Voucher Not Found!\n'
                            'Voucher %(number)s of pos %(pos_name)s has not been found.'
                        ),
                        number=number,
                        pos_name=self.pos_id.name,
                    )

                invoices += invoice

                date_invoice = time.strftime(
                    DEFAULT_SERVER_DATE_FORMAT,
                    time.strptime(str(res['CbteFch']), '%Y%m%d'),
                )
                cae_due_date = time.strftime(
                    DEFAULT_SERVER_DATE_FORMAT,
                    time.strptime(str(res['FchVto']), '%Y%m%d'),
                )
                cae = str(res['CodAutorizacion'])

                invoice.wsfe_relate_invoice(
                    pos, number, date_invoice, cae, cae_due_date
                )

                # if self.env.context.get('commit', True):
                #     cr.commit()

            if invoices:
                act_window = {
                    'name': _('Updated Invoices'),
                    'type': 'ir.actions.act_window',
                    'res_model': 'account.move',
                    'view_type': 'form',
                    'view_mode': 'tree,form',
                    'target': 'current',
                    'domain': [('id', 'in', invoices.ids)],
                }
                return act_window
            else:
                return {'type': 'ir.actions.act_window_close'}
