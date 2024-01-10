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
        shipping_perm = 'N'
        if tipo_cbte in ('20', '21') or (
            tipo_cbte == '19' and export_type in (2, 4)
        ):
            shipping_perm = ''
        elif invoice.shipping_perm_ids:
            shipping_perm = 'S'
        return shipping_perm

    def _get_date_due(self, invoice, tipo_cbte, export_type):
        """
        Para comprobantes del tipo “19 - Facturas de Exportación” donde el tipo de exportación es
        2 Servicios / 4 Otros es obligatoria.

        Para comprobantes que no son tipo “19 - Facturas de Exportación” no debe informarse.

        Para comprobantes del tipo “19 - Facturas de Exportación” donde el tipo de exportación es
        2 Servicios / 4 Otros, debe ser igual o posterior a la fecha de emisión del comprobante.
        """
        date_due = None
        if tipo_cbte == '19' and export_type in (2, 4):
            if invoice.invoice_date_due < invoice.invoice_date:
                raise UserError(
                    _(
                        "Due date must be after invoice date for invoice id: %(id)s.",
                        id=invoice.id,
                    )
                )
            date_due = (
                invoice.invoice_date_due
                and self._convert_date_to_AFIP_format(invoice.invoice_date_due)
            )
        return date_due

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
        pais_dst = int(invoice.dst_country_id.code)
        dst_cuit = None
        if invoice.partner_id.dst_cuit_id:
            dst_cuit = invoice.partner_id.dst_cuit_id.code
        partner_cuit = invoice.partner_id.vat
        if not dst_cuit and not partner_cuit:
            raise UserError(
                _(
                    "This partner %(name)s doesn't have DST CUIT or VAT configured.",
                    name=invoice.partner_id.name,
                )
            )

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
        partner_name = "DFSDFSDSD"
        partner_address = "DFSDFSDSD"

        date_due = self._get_date_due(invoice, tipo_cbte, export_type)
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
                'DocNro': partner_cuit,
                'FchVtoPago': date_due,
                'MonId': currency_code,
                'MonCotiz': invoice_rate,
                'expo_type': export_type,
                'exist_perm': has_shipping_perm,
                'pais_dst': pais_dst,
                'cuit_pais': dst_cuit,
                'partner_cuit': partner_cuit,
                'partner_name': partner_name,
                'partner_address': partner_address,
                'lang': str(
                    1
                ),  # TODO: add field to account.move to use wsfex tables
            }
        )
        return subtotals

    def parse_items(self, invoice):
        items = []
        for line in invoice.invoice_line_ids:
            uom_codes = invoice.env['wsfex.uom.codes'].search(
                [('uom_id', '=', line.product_uom_id.id)]
            )
            if not uom_codes:
                raise UserError(
                    _(
                        """
                        WSFEX Error!
                        There is no UoM Code defined for %(uom_name)s in line %(line_name)s
                        """
                    ),
                    uom_name=line.product_uom_id.name,
                    line_name=line.name,
                )

            uom_code = uom_codes[0].code

            items.append(
                {
                    'Pro_codigo': line.product_id.default_code or '',
                    'Pro_ds': (
                        line.name.encode('latin-1', errors='ignore')
                        .decode('utf8')
                        .replace('\n', ' ')
                    ),
                    'Pro_qty': line.quantity,
                    'Pro_umed': uom_code,
                    'Pro_precio_uni': line.price_unit,
                    'Pro_total_item': line.price_subtotal,
                    'Pro_bonificacion': line.discount,
                }
            )
        return items

    def parse_permissions(self, invoice):
        permissions = []
        for permission in invoice.shipping_perm_ids:
            permissions.append(
                {
                    'id': permission.name,
                    'dest': int(permission.dst_country_id.code),
                }
            )
        return permissions
