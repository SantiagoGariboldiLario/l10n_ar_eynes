##############################################################################
#   Copyright (c) 2019 Eynes/E-MIPS (www.eynes.com.ar)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
##############################################################################

import logging

from odoo import _
from odoo.exceptions import UserError

from .ws_afip import WSParser

_logger = logging.getLogger(__name__)


class WSFEXParser(WSParser):
    def _check_shipping_perm(self, invoice, tipo_cbte, export_type):
        """
        Valores posibles: S, N o “vacío”
        “S” si ya se dispone del despacho de exportación.
        “N” si aún no se dispone del despacho de exportación.
        “vacío” si el campo Cbte_Tipo es 20 ó 21 o si Cbte_Tipo es igual a 19 y
        el campo Tipo_expo es igual a 2 ó 4.
        """
        if tipo_cbte in ('20', '21') or (
            tipo_cbte == '19' and export_type in (2, 4)
        ):
            shipping_perm = None
        else:
            shipping_perm = 'S' and invoice.shipping_perm_ids or 'N'
        return shipping_perm

    def parse_invoice(self, invoice):
        tipo_cbte = invoice.get_voucher_type()
        pto_vta = invoice.get_pos()
        invoice_date = (
            invoice.invoice_date
            and self._convert_date_to_AFIP_format(invoice.invoice_date)
            or False
        )
        export_type = int(invoice.export_type_id.code)
        has_shipping_perm = self._check_shipping_perm(
            invoice, tipo_cbte, export_type
        )
        pais_dst = invoice.dst_country_id.code
        if not invoice.partner_id.dst_cuit_id:
            raise UserError(
                _("This partner %(name)s doesn't have "),
                name=invoice.partner_id.name,
            )
        cuit_pais = invoice.partner_id.dst_cuit_id.code
        partner_name = invoice.partner_id.name.encode(
            'latin-1', errors='ignore'
        ).decode('utf8')
        partner_address = (
            invoice.partner_id.contact_address.encode(
                'latin-1', errors='ignore'
            )
            .decode('utf8')
            .replace('\n', ' ')
        )

        doc_type = (
            invoice.partner_id.document_type_id
            and invoice.partner_id.document_type_id.afip_code
            or '99'
        )
        doc_num = (invoice.partner_id.vat or '0') if doc_type != '99' else '0'
        date_due = self._get_date_due(invoice, invoice_date)
        currency_code = invoice.get_currency_code()
        invoice_rate = invoice.currency_rate

        subtotals = {
            'total_amount': invoice.amount_total,
        }

        self._afip_round(subtotals)

        subtotals.update(
            {
                'CbteTipo': tipo_cbte,
                'PtoVta': pto_vta,
                'CbteFch': invoice_date,
                'DocNro': doc_num,
                'FchVtoPago': date_due,
                'MonId': currency_code,
                'MonCotiz': invoice_rate,
                'expo_type': export_type,
                'exist_perm': has_shipping_perm,
                'pais_dst': pais_dst,
                'cuit_pais': cuit_pais,
                'partner_name': partner_name,
                'partner_address': partner_address,
                'lang': 1,  # TODO: add field to account.move to use wsfex tables
            }
        )
        return subtotals

    def parse_items(self, invoice):
        items = []
        for line in invoice.invoice_line_ids:
            uom_codes = invoice.env['wsfex.uom.codes'].search(
                [('uom_id', '=', line.uom_id.id)]
            )
            if not uom_codes:
                raise UserError(
                    _(
                        """
                        WSFEX Error!
                        There is no UoM Code defined for %(uom_name)s in line %(line_name)s
                        """
                    ),
                    uom_name=line.uom_id.name,
                    line_name=line.name,
                )

            uom_code = uom_codes[0].code

            items.append(
                {
                    'Pro_codigo': line.product_id.default_code or '',
                    'Pro_ds': line.name.encode(
                        'ascii', errors='ignore'
                    ).decode(),
                    'Pro_qty': line.quantity,
                    'Pro_umed': uom_code,
                    'Pro_precio_uni': line.price_unit,
                    'Pro_total_item': line.price_subtotal,
                    'Pro_bonificacion': self.discount,
                }
            )
        return items

    def parse_associated_voucher(self, invoice):
        CbtesAsoc = []
        for associated_inv in invoice.associated_inv_ids:
            tipo_cbte = associated_inv.get_voucher_type()
            pos, number = associated_inv.name.split('-')
            CbteAsoc = {
                'Tipo': tipo_cbte,
                'PtoVta': int(pos),
                'Nro': int(number),
                'Cuit': invoice.company_id.partner_id.vat,
            }
            CbtesAsoc.append(CbteAsoc)
        return CbtesAsoc

    def parse_permissions(self, invoice):
        permissions = []
        for permission in invoice.shipping_perm_ids:
            permissions.append(
                {
                    'id': permission.name,
                    'dest': permission.dst_country_id.code,
                }
            )
        return permissions
