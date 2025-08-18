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

    def _check_vat_taxes_configured(self, afip_tax_ids, invoice_taxes):
        not_found_tax = invoice_taxes.filtered(lambda x: x not in afip_tax_ids)
        if not_found_tax:
            raise UserError(
                _("Taxes `%s` are not configured in WSFE!")
                % (", ").join(not_found_tax.mapped('name'))
            )

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
        fiscal_position = invoice.partner_id.property_account_position_id
        if not fiscal_position:
            raise UserError(
                _("You must configure a fiscal position for %s")
                % invoice.partner_id.name
            )
        try:
            fiscal_position = int(fiscal_position.afip_code)
        except ValueError:
            raise UserError(
                _(
                    "You must select a valid AFIP Code for fiscal position for %s"
                )
                % invoice.partner_id.property_account_position_id.name
            ) from None
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
                'CanMisMonExt': 'S' if invoice.same_currency_cancel else 'N',
                'CondicionIVAReceptorId': fiscal_position,
                'FchServDesde': date_from,
                'FchServHasta': date_to,
            }
        )
        return subtotals

    def parse_vat_lines(self, invoice, afip_taxes):
        invoice_taxes = invoice.invoice_line_ids.tax_ids.filtered(
            lambda tax: tax.tax_group_id.group_type == 'vat'
        )
        self._check_vat_taxes_configured(
            afip_taxes.mapped('tax_id'), invoice_taxes
        )

        vat_dict = {}
        for tax in invoice_taxes:
            afip_tax = afip_taxes.filtered(lambda x: x.tax_id == tax)
            if len(afip_tax) > 1:
                raise UserError(
                    _(
                        """
                        This vat: %(vat_name)s has more than one configuration.
                        """,
                        vat_name=tax.name,
                    )
                )

            code = int(afip_tax.code)

            if code == 3:
                lines = invoice.invoice_line_ids.filtered(
                    lambda line: tax in line.tax_ids
                )
                amount = 0.0
                base = sum(lines.mapped('price_subtotal'))
            else:
                tax_line = invoice.line_ids.filtered(
                    lambda line: tax == line.tax_line_id
                )
                amount = (
                    tax_line.credit or tax_line.debit
                ) * tax_line.currency_rate
                base = (tax_line.tax_base_amount) * tax_line.currency_rate
            if code not in vat_dict:
                vat_dict[code] = {
                    'Importe': amount,
                    'BaseImp': base,
                }
            else:
                vat_dict[code]['Importe'] += amount
                vat_dict[code]['BaseImp'] += base

        vals = {
            'vat_dict': vat_dict,
            'total_vat_amount': sum(x['Importe'] for x in vat_dict.values()),
            'base_vat_amount': sum(x['BaseImp'] for x in vat_dict.values()),
        }
        self._afip_round(vals)
        return vals

    def parse_taxes_not_vat(self, invoice):
        PCODES = {
            'nacional': '1',
            'provincial': '2',
            'municipal': '3',
            'interno': '4',
        }
        tributes_array = []

        tribute_total = 0
        for perception in invoice.perception_ids:
            code = int(PCODES[perception.perception_id.jurisdiccion])
            perc = {
                'Id': code,
                'BaseImp': perception.base,
                'Importe': perception.amount,
                'Alic': 0.0,
                'Desc': perception.name,
            }
            tribute_total += perc['Importe']
            tributes_array.append(perc)

        for internal in invoice.internal_taxes_ids:
            perc = {
                'Id': PCODES['interno'],
                'BaseImp': internal.base,
                'Importe': internal.amount,
                'Alic': 0.0,
                'Desc': internal.name,
            }
            tribute_total += perc['Importe']
            tributes_array.append(perc)

        vals = {
            'tributes_array': tributes_array,
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

    def parse_associated_period(self, invoice):
        CbtesAsoc = []
        if invoice.inform_period:
            from_date = self._convert_date_to_AFIP_format(
                invoice.inform_period_date_from
            )
            to_date = self._convert_date_to_AFIP_format(
                invoice.inform_period_date_to
            )
            CbteAsoc = {
                'from': from_date,
                'to': to_date,
            }
            CbtesAsoc.append(CbteAsoc)
        return CbtesAsoc

    def parse_optionals(self, invoice):
        optionals = []
        for optional in invoice.optional_ids:
            optional_code = int(optional.optional_id.code)
            if optional.value:
                optionals.append(
                    {
                        'Code': optional_code,
                        'Valor': optional.value.strip(),
                    }
                )
            else:
                raise UserError(
                    _(
                        'You must set a value for Optional code %(code)s',
                        code=optional_code,
                    )
                )
        return optionals

    def get_cae_due_date(self, ws, error_msg):
        cae_due_date = False
        try:
            if ws.Vencimiento:
                cae_due_date = datetime.strptime(
                    ws.Vencimiento, "%Y%m%d"
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

    def get_invoice_name(self, env, voucher_type, ws, error_msg):
        invoice_name = False
        try:
            invoice_name = "%s%s-%s" % (
                self.handle_FCE_prefix(env, voucher_type),
                str(ws.PuntoVenta).zfill(5),
                str(ws.CbteNro).zfill(8),
            )
        except Exception as e:
            error_msg += str(e)
            error_msg += '. Invoice number not saved \n'
        return invoice_name, error_msg

    def handle_FCE_prefix(self, env, voucher_type):
        if voucher_type in [
            int(
                env.ref('l10n_ar_eynes.factura_credito_electronica_a').afip_code
            ),
            int(
                env.ref('l10n_ar_eynes.factura_credito_electronica_b').afip_code
            ),
        ]:
            return 'FCE'
        elif voucher_type in [
            int(env.ref('l10n_ar_eynes.nota_credito_electronica_a').afip_code),
            int(env.ref('l10n_ar_eynes.nota_credito_electronica_b').afip_code),
        ]:
            return 'NCE'
        elif voucher_type in [
            int(
                env.ref('l10n_ar_eynes.factura_debito_electronica_a').afip_code
            ),
            int(
                env.ref('l10n_ar_eynes.factura_debito_electronica_b').afip_code
            ),
        ]:
            return 'NDE'
        return ''
