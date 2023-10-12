##############################################################################
#   Copyright (c) 2018 Eynes/E-MIPS (www.eynes.com.ar)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
##############################################################################

import logging
from datetime import datetime

from odoo import _
from odoo.exceptions import UserError

from .ws_afip import WSParser

_logger = logging.getLogger(__name__)

# self._convert_date_to_AFIP_format()


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
        ** AFIP DOC: Fecha de vencimiento del pago servicio
        a facturar. Dato obligatorio para
        concepto 2 o 3 (Servicios / Productos y
        Servicios) o Facturas del tipo MiPyMEs
        (FCE). Formato yyyymmdd. Debe ser
        igual o posterior a la fecha del
        comprobante
        """
        date_due = False
        if (concept in [2, 3] and not date_due) or invoice.is_FCE_invoice:
            date_due = (
                invoice.invoice_date_due
                and self._convert_date_to_AFIP_format(invoice.invoice_date_due)
                or self._convert_date_to_AFIP_format(datetime.today())
            )
        return date_due

    def _get_date_from(self, invoice, concept, invoice_date):
        date_from = False
        if concept in [2, 3]:
            # date_from = invoice.date_from and
            # self._convert_date_to_AFIP_format(invoice.date_from) or False
            if not date_from:
                date_from = self._convert_date_to_AFIP_format(invoice_date)
        return date_from

    def _get_date_to(self, invoice, concept, invoice_date):
        date_to = False
        if concept in [2, 3]:
            # date_from = invoice.date_to and
            # self._convert_date_to_AFIP_format(invoice.date_to) or False
            if not date_to:
                date_to = self._convert_date_to_AFIP_format(invoice_date)
        return date_to

    def parse_invoice(self, invoice):
        tipo_cbte = invoice.get_voucher_type()
        pto_vta = invoice.get_pos()
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
        date_from = self._get_date_from(invoice, concept, invoice_date)
        date_to = self._get_date_to(invoice, concept, invoice_date)

        subtotals = {
            'exempt_amount': invoice.amount_exempt,
            'no_taxed_amount': invoice.amount_no_taxed,
            'total_amount': invoice.amount_total,
        }

        self._afip_round(subtotals)

        subtotals.update(
            {
                'CbteTipo': tipo_cbte,
                'PtoVta': pto_vta,
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
                    if not invoice.is_company_cur
                    else tax_line.tax_base_amount,
                }
            else:
                vat_dict[code]['Importe'] += tax_line.price_unit
                if invoice.is_company_cur:
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
                'BaseImp': round(perception.base / invoice.currency_rate, 2)
                if not invoice.is_company_cur
                else perception.base,
                'Importe': round(perception.amount / invoice.currency_rate, 2)
                if not invoice.is_company_cur
                else perception.amount,
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
            pos, number = associated_inv.name.split('-')
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

    def parse_errors(self, ws, title):
        error_msg = ""
        if ws.Errores:
            error_msg += _(
                """
                Error trying to %(title)s.
                """,
                title=title,
            )
            for error in ws.Errores:
                error_msg += error
        if ws.Eventos:
            error_msg += _(
                """
                Events trying to %(title)s.
                """,
                title=title,
            )
            for event in ws.Eventos:
                error_msg += event

        if error_msg:
            _logger.info(error_msg)
            raise UserError(error_msg)


# # FIELD VALIDATION RULES FOR AFIP:
# NATURALS = [
#     'CantReg',
#     'CbteTipo',
#     'PtoVta',
#     'DocTipo',
#     'CbteHasta',
#     'CbteNro',
#     'Id',
# ]

# POSITIVE_REALS = [
#     'ImpTotal',
#     'ImpTotConc',
#     'ImpNeto',
#     'ImpOpEx',
#     'ImpIVA',
#     'ImpTrib',
#     'BaseImp',
#     'Importe',
# ]

# STRINGS = ['MonId']

# class WSFEValidator():

# def _check_CbteFch(self, invoice):
#         """
#         Fecha del comprobante (yyyymmdd).
#         Para concepto igual a 1, la fecha de
#         emisión del comprobante puede ser hasta
#         5 días anteriores o posteriores respecto
#         de la fecha de generación: La misma no
#         podrá exceder el mes de presentación. Si
#         se indica Concepto igual a 2 ó 3 puede
#         ser hasta 10 días anteriores o posteriores
#         a la fecha de generación.
#         Para comprobantes del tipo MiPyMEs
#         (FCE) del tipo Factura, la fecha de
#         emisión del comprobante debe ser desde
#         5 días anteriores y hasta 1 día posterior
#         respecto de la fecha de generación. Para
#         notas de débito y crédito es hasta 5 dias
#         anteriores y tiene que ser posterior o igual
#         a la fecha del comprobante asociado.

#         Si no se envía
#         la fecha del comprobante se asignará la
#         fecha de proceso.

#         """
#         invoice_date = invoice.invoice_date
#         today = datetime.today()

#     @staticmethod
#     @WsApi.check(['DocNro'], reraise=True, sequence=20)
#     def validate_docnro(val, invoice, DocTipo):
#         tin_type = int(DocTipo)
#         if tin_type != 99:
#             tin_number = int(val)
#         else:
#             tin_number = val
#         if invoice.denomination == 'b':
#             if tin_type != 99 and not tin_number:
#                 return False
#             if invoice.amount_total >= 5000:
#                 if not tin_number:
#                     return False
#             else:
#                 if tin_type == 99 and tin_number != '0':
#                     return False
#         if invoice.denomination == 'a':
#             if not int(val):
#                 return False
#         return True

#     @staticmethod
#     @WsApi.check(['CbteDesde'], reraise=True, sequence=20)
#     def validate_invoice_number(val, invoice, invoices, first_of_lot=True):
#         return True

#     @staticmethod
#     @WsApi.check(NATURALS)
#     def validate_natural_number(val):
#         val = int(val)
#         if val > 0:
#             return True
#         return False

#     @staticmethod
#     @WsApi.check(POSITIVE_REALS)
#     def validate_positive_reals(val):
#         if not val or (isinstance(val, float) and val > 0):
#             return True
#         return False

#     @staticmethod
#     @WsApi.check(STRINGS)
#     def validate_strings(val):
#         if isinstance(val, str):
#             return True
#         return False

#     @staticmethod
#     @WsApi.check(['Concepto'])
#     def validate_concept(val):
#         if val in [1, 2, 3]:
#             return True
#         return False

#     @staticmethod
#     @WsApi.check(['FchServDesde'])
#     def validate_service_from_date(val, Concepto):
#         if Concepto not in [2, 3]:
#             return True
#         datetime.strptime(val, AFIP_DATE_FORMAT)
#         return True

#     @staticmethod
#     @WsApi.check(['FchServHasta'])
#     def validate_service_to_date(val, FchServDesde, Concepto):
#         if Concepto not in [2, 3]:
#             return True
#         datetime.strptime(val, AFIP_DATE_FORMAT)
#         if val >= FchServDesde:
#             return True
#         return False

#     @staticmethod
#     @WsApi.check(['FchVtoPago'])
#     def validate_service_payment_date(val, invoice, Concepto):
#         if Concepto not in [2, 3]:
#             return True
#         # No checks if invoice is of mipyme.fcred
#         if invoice.is_FCE_invoice:
#             return True
#         datetime.strptime(val, AFIP_DATE_FORMAT)
#         inv_date = invoice.invoice_date or fields.Date.context_today(invoice)
#         inv_date = inv_date.strftime(AFIP_DATE_FORMAT)
#         if val >= inv_date.replace('-', ''):
#             return True
#         return False

#     @staticmethod
#     @WsApi.check(['CbteFch'], reraise=True)
#     def validate_invoice_date(val, invoice, Concepto):
#         if not val:
#             return True
#         if invoice.state == 'posted':
#             return True
#         val_date = datetime.strptime(val, AFIP_DATE_FORMAT)
#         last_invoiced_date = invoice.get_last_date_invoice()
#         conf = invoice.get_ws_conf()

#         if last_invoiced_date and val_date.date() < last_invoiced_date:
#             raise UserError(
#                 _('WSFE Error!\n')
#                 + _(
#                     'There is another Invoice with a most recent date [%s] '
#                     + 'for the same Point of Sale and Denomination.'
#                 )
#                 % last_invoiced_date
#             )
#         today = fields.Date.context_today(invoice)
#         offset = today - val_date.date()
#         if Concepto in [2, 3]:
#             if abs(offset.days) > conf.services_date_difference:
#                 raise UserError(
#                     _('WSFE Error!\n')
#                     + _(
#                         'Invoice Date difference with today should be less '
#                         + 'than [%s] days for products and services sales.'
#                     )
#                     % conf.services_date_difference
#                 )
#         else:
#             if abs(offset.days) > conf.products_date_difference:
#                 raise UserError(
#                     _('WSFE Error!\n')
#                     + _(
#                         'Invoice Date difference with today should be less '
#                         + 'than [%s] days for product sales.'
#                     )
#                     % conf.products_date_difference
#                 )
#         return True

#     @staticmethod
#     @WsApi.check(['MonCotiz'])
#     def validate_currency_rate(val, MonId):
#         if MonId == 'PES':
#             if val == 1:
#                 return True
#         else:
#             if isinstance(val, float):
#                 return True
#         return False

#     @staticmethod
#     @WsApi.check(['Tipo', 'Nro'])
#     def validate_cmps_tipo(val, Tipo):
#         return True

#     @staticmethod
#     @WsApi.check(['Valor'])
#     def validate_cmps_valor(val, Valor):
#         return True

#     @staticmethod
#     @WsApi.check(['Alic', 'Desc'])
#     def validate_tributos(val, Alic):
#         return True
