##############################################################################
#   Copyright (c) 2019 Eynes/E-MIPS (www.eynes.com.ar)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
##############################################################################

import logging
from datetime import datetime

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
        if tipo_cbte in (20, 21) or (tipo_cbte == 19 and export_type in (2, 4)):
            shipping_perm = ''
        else:
            shipping_perm = 'S' and invoice.shipping_perm_ids or 'N'
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
        if tipo_cbte == 19 and export_type in (2, 4):
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
        dst_cuit = invoice.partner_id.vat
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

        partner_name = invoice.partner_id.name
        partner_address = invoice.partner_id.contact_address

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
                'CanMisMonExt': 'S' if invoice.same_currency_cancel else 'N',
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
                        """,
                        uom_name=line.product_uom_id.name,
                        line_name=line.name,
                    )
                )

            items.append(
                {
                    'Pro_codigo': line.product_id.default_code or '',
                    'Pro_ds': line.name,
                    'Pro_qty': line.quantity,
                    'Pro_umed': uom_codes[0].code,
                    'Pro_precio_uni': line.price_unit,
                    'Pro_total_item': line.price_subtotal,
                    'Pro_bonificacion': round(
                        line.quantity * line.price_unit * line.discount / 100, 2
                    ),
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

    def get_cae_due_date(self, ws, error_msg):
        cae_due_date = False
        try:
            if ws.Vencimiento:
                cae_due_date = datetime.strptime(
                    ws.Vencimiento, "%d/%m/%Y"
                ).date()
        except Exception as e:
            error_msg += str(e)
            error_msg += '. CAE Due Date not saved \n'
        return cae_due_date, error_msg

    def get_invoice_date(self, ws, error_msg):
        invoice_date = False
        try:
            if ws.FechaCbte:
                invoice_date = datetime.strptime(ws.FechaCbte, "%Y%m%d").date()
        except Exception as e:
            error_msg += str(e)
            error_msg += '. Invoice Date not saved \n'
        return invoice_date, error_msg

    def get_invoice_name(self, ws, pos, error_msg):
        invoice_name = False
        try:
            invoice_name = "%s-%s" % (
                str(pos).zfill(5),
                str(ws.CbteNro).zfill(8),
            )
        except Exception as e:
            error_msg += str(e)
            error_msg += '. Invoice number not saved \n'
        return invoice_name, error_msg
