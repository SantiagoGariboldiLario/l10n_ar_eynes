##############################################################################
#   Copyright (c) 2018 Eynes/E-MIPS (www.eynes.com.ar)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
##############################################################################

import logging
import re
from datetime import datetime

from odoo import _
from odoo.exceptions import UserError

from .ws_afip import WSParser

_logger = logging.getLogger(__name__)


class WSFEParser(WSParser):
    def _get_concept(self, invoice):
        product_service = [
            line.product_id and line.product_id.type or 'consu'
            for line in invoice.invoice_line_ids
        ]
        service = all([ps == 'service' for ps in product_service])
        products = all(
            [ps == 'consu' or ps == 'product' for ps in product_service]
        )
        concept = 3  # Products and Services
        if products:
            concept = 1  # Products
        elif service:
            concept = 2  # Services
        return concept

    def _get_date_due(self, invoice, concept, invoice_date):
        """
        ** AFIP DOC: Fecha de vencimiento del pago servicio a facturar. Dato obligatorio para concepto 2 o 3
        (Servicios / Productos y Servicios) o Facturas del tipo MiPyMEs (FCE). Formato yyyymmdd.
        Debe ser igual o posterior a la fecha del comprobante.
        Si el tipo de comprobante que está autorizando es MiPyMEs (FCE), no debe informarse si NO es Factura de Crédito.
        En el caso de ser Débito o Crédito, solo puede informarse si es de Anulación.
        """
        date_due = False
        voucher_type_FCEA = invoice.env.ref(
            'l10n_ar_eynes.factura_credito_electronica_a'
        )
        voucher_type_FCEB = invoice.env.ref(
            'l10n_ar_eynes.factura_credito_electronica_b'
        )
        is_services = concept in [2, 3]
        is_FCE = invoice.voucher_type_id in [
            voucher_type_FCEA,
            voucher_type_FCEB,
        ]
        is_cancellation = invoice.optional_ids.filtered(
            lambda opt: opt.code == '22' and opt.value == 'S'
        )
        if (
            (is_services and not invoice.is_FCE_invoice)
            or is_FCE
            or is_cancellation
        ):
            date_due = (
                invoice.invoice_date_due
                and self._convert_date_to_AFIP_format(invoice.invoice_date_due)
                or self._convert_date_to_AFIP_format(datetime.today())
            )
        return date_due

    def _get_date_from(self, invoice, concept):
        date_from = False
        if concept in [2, 3]:
            # TODO: add this field to invoice
            # date_from = invoice.date_from and
            # self._convert_date_to_AFIP_format(invoice.date_from) or False
            if not date_from:
                date_from = self._convert_date_to_AFIP_format(
                    invoice.invoice_date
                )
        return date_from

    def _get_date_to(self, invoice, concept):
        date_to = False
        if concept in [2, 3]:
            # TODO: add this field to invoice
            # date_from = invoice.date_to and
            # self._convert_date_to_AFIP_format(invoice.date_to) or False
            if not date_to:
                date_to = self._convert_date_to_AFIP_format(
                    invoice.invoice_date
                )
        return date_to

    def parse_invoice(self, invoice):
        tipo_cbte = invoice.get_voucher_type()
        invoice_date = (
            invoice.invoice_date
            and self._convert_date_to_AFIP_format(invoice.invoice_date)
            or False
        )
        concept = self._get_concept(invoice)
        doc_type = (
            invoice.partner_id.document_type_id
            and invoice.partner_id.document_type_id.afip_code
            or '99'
        )
        doc_num = (invoice.partner_id.vat or '0') if doc_type != '99' else '0'
        date_due = self._get_date_due(invoice, concept, invoice_date)
        currency_code = invoice.get_currency_code()
        invoice_rate = invoice.currency_rate
        date_from = self._get_date_from(invoice, concept)
        date_to = self._get_date_to(invoice, concept)

        subtotals = {
            'exempt_amount': invoice.amount_exempt,
            'no_taxed_amount': invoice.amount_no_taxed,
            'total_amount': invoice.amount_total,
        }

        self._afip_round(subtotals)

        subtotals.update(
            {
                'CbteTipo': tipo_cbte,
                'CbteFch': invoice_date,
                'Concepto': concept,
                'DocTipo': doc_type,
                'DocNro': doc_num,
                'FchVtoPago': date_due,
                'MonId': currency_code,
                'MonCotiz': invoice_rate,
                'FchServDesde': date_from,
                'FchServHasta': date_to,
            }
        )
        return subtotals

    def parse_vat_lines(self, invoice, vat_lines, afip_taxes):
        vat_dict = {}
        for tax_line in vat_lines:
            afip_tax = afip_taxes.filtered(
                lambda x: x.tax_id == tax_line.tax_line_id
            )
            if len(afip_tax) > 1:
                raise UserError(
                    _(
                        """
                        This vat: %(vat_name)s has more than one configuration.
                        """,
                        vat_name=tax_line,
                    )
                )
            code = int(afip_tax.code)
            if code not in vat_dict:
                vat_dict[code] = {
                    'Importe': tax_line.price_unit,
                    'BaseImp': tax_line.tax_base_amount / invoice.currency_rate
                    if invoice.is_multi_currency
                    else tax_line.tax_base_amount,
                }
            else:
                vat_dict[code]['Importe'] += tax_line.price_unit
                if not invoice.is_multi_currency:
                    vat_dict[code]['BaseImp'] += tax_line.tax_base_amount
                else:
                    vat_dict[code]['BaseImp'] += (
                        tax_line.tax_base_amount / invoice.currency_rate
                    )

        vals = {
            'vat_dict': vat_dict,
            'total_vat_amount': sum(x['Importe'] for x in vat_dict.values()),
            'base_vat_amount': sum(x['BaseImp'] for x in vat_dict.values()),
        }
        self._afip_round(vals)
        return vals

    def parse_taxes_not_vat(self, invoice):
        PCODES = {'nacional': '1', 'provincial': '2', 'municipal': '3'}
        perc_array = []

        tribute_total = 0
        for perception in invoice.perception_ids:
            code = int(PCODES[perception.perception_id.tax_id.jurisdiccion])
            perc = {
                'Id': code,
                'BaseImp': perception.base,
                'Importe': perception.amount,
                'Alic': 0.0,
                'Desc': perception.name,
            }
            tribute_total += perc['Importe']
            perc_array.append(perc)

        vals = {
            'perc_array': perc_array,
            'tribute_total': tribute_total,
        }
        self._afip_round(vals)
        return vals

    def parse_associated_voucher(self, invoice):
        CbtesAsoc = []
        for associated_inv in invoice.associated_inv_ids:
            tipo_cbte = associated_inv.get_voucher_type()

            inv_name = associated_inv.name
            pattern = re.compile(r'(FCE|NCE|NDE)')
            match = pattern.search(associated_inv.name)
            if match:
                inv_name = inv_name.replace(match.group(), '')
            pos, number = inv_name.split('-')

            cbte_fch = self._convert_date_to_AFIP_format(
                associated_inv.invoice_date
            )
            CbteAsoc = {
                'Tipo': tipo_cbte,
                'PtoVta': int(pos),
                'Nro': int(number),
                'Cuit': invoice.company_id.partner_id.vat,
                'CbteFch': cbte_fch,
            }
            CbtesAsoc.append(CbteAsoc)
        return CbtesAsoc

    def parse_optionals(self, invoice):
        if invoice.optional_ids:
            return invoice.optional_ids.mapped(
                lambda o: {
                    'Code': int(o.optional_id.code),
                    'Valor': o.value.strip(),
                }
            )
        return []
