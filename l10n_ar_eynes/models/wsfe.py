##############################################################################
#   Copyright (c) 2018 Eynes/E-MIPS (www.eynes.com.ar)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
##############################################################################

import logging

from pyafipws.wsfev1 import WSFEv1
from pysimplesoap.client import SoapFault

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..wsfetools.wsfe_helper import WSFEParser

_logger = logging.getLogger(__name__)

SEPARATOR = ";"


class WsfeConfig(models.Model):
    _name = "wsfe.config"
    _inherit = "ws.config"
    _description = "Configuration for WSFE"

    _webservice_class = WSFEv1

    currency_ids = fields.One2many(
        comodel_name='ws.currency.codes',
        inverse_name='wsfe_config_id',
        string='Currencies',
        domain=[('from_afip', '=', True)],
    )
    exempt_operations_tax_ids = fields.One2many(
        comodel_name='ws.tax.codes',
        inverse_name='wsfe_config_id',
        string='Taxes of Exempt Operations',
        domain=[('from_afip', '=', False), ('exempt_operations', '=', True)],
    )
    optional_ids = fields.One2many(
        comodel_name='ws.optionals',
        inverse_name='wsfe_config_id',
        string='Optionals',
        domain=[('from_afip', '=', True)],
    )
    point_of_sale_ids = fields.One2many(
        comodel_name='ws.pos.line',
        inverse_name='wsfe_config_id',
        string='POS',
        domain=[('from_afip', '=', True)],
    )
    vat_tax_ids = fields.One2many(
        comodel_name='ws.tax.codes',
        inverse_name='wsfe_config_id',
        string='Taxes',
        domain=[('from_afip', '=', True)],
    )

    @api.depends('config_id', 'config_id.homologation')
    def _compute_url(self):
        url_prod = self.env.ref('l10n_ar_eynes.url_prod_wsfe').value.rstrip()
        url_homo = self.env.ref('l10n_ar_eynes.url_homo_wsfe').value.rstrip()
        for rec in self:
            rec.url = url_homo if rec.config_id.homologation else url_prod

    def _get_webservice(self):
        return self.env.ref('l10n_ar_eynes.afipws_service_wsfe')

    def unlink(self):
        self.env['ws.currency.codes'].search(
            [('wsfe_config_id', '=', self.id)]
        ).unlink()
        self.env['ws.optionals'].search(
            [('wsfe_config_id', '=', self.id)]
        ).unlink()
        self.env['ws.pos'].search([('wsfe_config_id', '=', self.id)]).unlink()
        self.env['ws.pos.line'].search(
            [('wsfe_config_id', '=', self.id)]
        ).unlink()
        self.env['ws.tax.codes'].search(
            [('wsfe_config_id', '=', self.id)]
        ).unlink()
        return super(WsfeConfig, self).unlink()

    def _create_records_from_afip_result(self, ws, result, model_to_create):
        helper = WSFEParser()
        vals_list = []
        for vat_data in result:
            code, name, from_date, to_date = vat_data.split(SEPARATOR)
            vals = {
                'code': code,
                'name': name,
            }
            if hasattr(model_to_create, 'from_date'):
                vals.update(
                    {
                        'from_date': helper.clean_result_date(from_date),
                    }
                )
            if hasattr(model_to_create, 'to_date'):
                vals.update(
                    {
                        'to_date': helper.clean_result_date(to_date),
                    }
                )
            if hasattr(model_to_create, 'from_afip'):
                vals.update(
                    {
                        'from_afip': True,
                    }
                )

            record = model_to_create.search(
                [
                    ('code', '=', code),
                    ('wsfe_config_id', '=', self.id),
                ]
            )
            if not record:
                vals.update(
                    {
                        'wsfe_config_id': self.id,
                    }
                )
                vals_list.append(vals)
            else:
                record.write(vals)
        model_to_create.create(vals_list)
        return helper.parse_errors(ws)

    def _get_currency_tables(self, ws):
        WsCurrencyCodes = self.env['ws.currency.codes']
        result = ws.ParamGetTiposMonedas(sep=SEPARATOR)
        error_msg = self._create_records_from_afip_result(
            ws=ws, result=result, model_to_create=WsCurrencyCodes
        )
        if error_msg:
            error_msg = 'Error getting Currency tables. Response:\n' + error_msg
        return error_msg

    def _get_vat_tables(self, ws):
        WsTaxCodes = self.env['ws.tax.codes']
        result = ws.ParamGetTiposIva(sep=SEPARATOR)
        error_msg = self._create_records_from_afip_result(
            ws=ws, result=result, model_to_create=WsTaxCodes
        )
        if error_msg:
            error_msg = 'Error getting Vat tables. Response:\n' + error_msg
        return error_msg

    def _get_optionals_tables(self, ws):
        WsOptionals = self.env['ws.optionals']
        result = ws.ParamGetTiposOpcional(sep=SEPARATOR)
        error_msg = self._create_records_from_afip_result(
            ws=ws, result=result, model_to_create=WsOptionals
        )
        if error_msg:
            error_msg = (
                'Error getting Optionals tables. Response:\n' + error_msg
            )
        return error_msg

    def _get_pos_tables(self, ws):
        WsPos = self.env['ws.pos']
        result = ws.ParamGetPtosVenta(sep=SEPARATOR)
        helper = WSFEParser()
        error_msg = helper.parse_errors(ws)

        vals_list = []
        for vat_data in result:
            helper = WSFEParser()
            code, name, blocked, to_date = vat_data.split(SEPARATOR)
            blocked = blocked.split(":")[1]
            to_date = to_date.split(":")[1]
            vals = {
                'code': code,
                'name': name,
                'blocked': False if blocked == 'N' else True,
                'to_date': helper.clean_result_date(to_date),
                'from_afip': True,
            }
            record = WsPos.search(
                [
                    ('code', '=', code),
                    ('wsfe_config_id', '=', self.id),
                ]
            )
            if not record:
                vals.update(
                    {
                        'wsfe_config_id': self.id,
                    }
                )
                vals_list.append(vals)
            else:
                record.write(vals)
        WsPos.create(vals_list)
        if error_msg:
            error_msg = 'Error getting POS tables. Response:\n' + error_msg
        return error_msg

    def get_afip_tables(self):
        self.ensure_one()
        if not self.cuit:
            raise UserError(_("Please configure the company VAT!"))

        ws = self.ws_auth()

        error_msg = self._get_currency_tables(ws)
        error_msg += self._get_optionals_tables(ws)
        error_msg += self._get_pos_tables(ws)
        error_msg += self._get_vat_tables(ws)

        if error_msg:
            raise UserError(
                _(
                    """
                    Error with Webservice
                    %(error_msg)s
                    """,
                    error_msg=error_msg,
                )
            )

        return True

    def get_currency_rate(self, invoice, request_id):
        """
        Devuelve la cotización de la moneda de la factura. Si la fecha es anterior o igual
        al día actual, se tomará la cotización del día anterior a dicha fecha.
        Si la fecha de la factura es posterior a la fecha actual, se tomará la cotización
        del día anterior a hoy.
        """
        self.ensure_one()
        if not self.cuit:
            raise UserError(_("Please configure the company VAT!"))

        helper = WSFEParser()
        mon_id = invoice.get_currency_code()

        today = fields.Date.today()
        invoice_date = invoice.invoice_date
        invoice_date = (
            invoice_date if invoice_date and invoice_date <= today else today
        )
        invoice_date = helper._get_last_working_day(invoice_date)
        date = (
            invoice_date
            and helper._convert_date_to_AFIP_format(invoice_date)
            or False
        )

        ws = None
        req_vals = {
            'invoice_id': invoice.id,
            'is_currency_request': True,
        }
        error_msg = xml_request = ""
        cotizacion = False
        try:
            ws = self.ws_auth()
            logging.info(
                "Send request to get currency rate of %s on %s"
                % (invoice.currency_id.name, date)
            )
            result = ws.FEParamGetCotizacion(mon_id, date)
            logging.info("Result: %s" % result)
            cotizacion = result and result.get("MonCotiz", False)
        except SoapFault as soap_fault:
            error_msg = "%s: %s" % (
                soap_fault.faultcode,
                soap_fault.faultstring,
            )
            _logger.exception("SOAP Error.")
            _logger.exception(error_msg)
        except Exception as e:
            if ws and ws.Excepcion:
                error_msg = ws.Excepcion
                _logger.exception("WSFE Error.")
                _logger.exception(error_msg)
            else:
                error_msg = str(e)
                _logger.exception("Internal Error.")
                _logger.exception(error_msg)
        finally:
            req_vals.update(
                {
                    'xml_request': xml_request,
                    'request_id': request_id,
                }
            )

        try:
            error_msg += '\n'.join(err for err in ws.Errores)
        except Exception as e:
            _logger.info(str(e))

        obs_msg = ''
        try:
            obs_msg = '\n'.join(obs for obs in ws.Observaciones)
        except Exception as e:
            _logger.info(str(e))

        events_msg = ''
        try:
            events_msg = '\n'.join(evn for evn in ws.Eventos)
        except Exception as e:
            _logger.info(str(e))

        if not error_msg and not events_msg:
            obs_msg += 'Se obtuvo la tasa de cambio desde ARCA al %s' % date

        req_vals.update(
            {
                'errors': error_msg,
                'events': events_msg,
                'observations': obs_msg,
            }
        )
        self.env['ws.request.detail'].create(req_vals)
        _logger.info("Request details saved.")
        self.env.cr.commit()  # pylint: disable=invalid-commit

        return cotizacion, error_msg + events_msg + obs_msg

    def _check_vat_taxes_configured(self, invoice_vat_lines):
        self.ensure_one()
        afip_taxes = self.vat_tax_ids.mapped('tax_id')

        not_found_tax = invoice_vat_lines.filtered(
            lambda x: x.tax_line_id not in afip_taxes
        )
        if not_found_tax:
            raise UserError(
                _("Taxes `%s` are not configured in WSFE!")
                % (", ").join(not_found_tax.mapped('tax_line_id.name'))
            )

    def _get_vat_array(self, invoice):
        invoice_vat_lines = invoice.line_ids.filtered(
            lambda x: x.tax_line_id
            and x.tax_group_id
            and x.tax_group_id.group_type == 'vat'
        )
        self._check_vat_taxes_configured(invoice_vat_lines)
        return invoice_vat_lines

    def _get_next_number(self, ws, tipo_cbte, pto_vta):
        _logger.info(
            "Checking last voucher informed to AFIP - Type: %s, POS: %s"
            % (tipo_cbte, pto_vta)
        )
        last_voucher_number = ws.CompUltimoAutorizado(tipo_cbte, pto_vta)
        helper = WSFEParser()
        helper.parse_errors_raise(ws, _("get the last voucher informed"))
        return int(last_voucher_number) + 1

    def get_voucher_info(self, pos, voucher_type, number):
        _logger.info(
            'Requesting data of voucher %s-%s-%s' % (pos, voucher_type, number)
        )
        self.ensure_one()
        ws = self.ws_auth()
        ws.CompConsultar(voucher_type, pos, number)
        helper = WSFEParser()
        helper.parse_errors_raise(ws, _("get voucher info"))
        ws.AnalizarXml('XmlResponse')
        res = {
            'DocTipo': ws.ObtenerTagXml('DocTipo'),
            'CbteFch': ws.ObtenerTagXml('CbteFch'),
            'FchVto': ws.ObtenerTagXml('FchVto'),
            'FchProceso': ws.ObtenerTagXml('FchProceso'),
            'DocNro': ws.ObtenerTagXml('DocNro'),
            'ImpTotal': ws.ObtenerTagXml('ImpTotal'),
            'ImpTotConc': ws.ObtenerTagXml('ImpTotConc'),
            'ImpNeto': ws.ObtenerTagXml('ImpNeto'),
            'ImpIVA': ws.ObtenerTagXml('ImpIVA'),
            'ImpTrib': ws.ObtenerTagXml('ImpTrib'),
            'ImpOpEx': ws.ObtenerTagXml('ImpOpEx'),
            'CodAutorizacion': ws.ObtenerTagXml('CodAutorizacion'),
        }
        _logger.info('Voucher info: %s' % res)
        return res

    def _match_invoice_pos(self, invoice):
        ws_pos = self.point_of_sale_ids.search(
            [
                ('journal_id', '=', invoice.journal_id.id),
                ('wsfe_config_id', '=', self.id),
            ],
            order="id desc",
            limit=1,
        )
        if not ws_pos:
            raise UserError(
                _(
                    "This journal '%(journal)s' is not configured in WSFE.",
                    journal=invoice.journal_id.name,
                )
            )
        return int(ws_pos.code)

    def _set_invoice_in_ws(self, ws, invoice):
        _logger.info("Parsing data from invoice ID: %s" % invoice.id)
        helper = WSFEParser()
        data = helper.parse_invoice(invoice)
        punto_vta = self._match_invoice_pos(invoice)
        vat_lines = self._get_vat_array(invoice)
        vat_data = helper.parse_vat_lines(invoice, vat_lines, self.vat_tax_ids)
        tribute_data = helper.parse_taxes_not_vat(invoice)
        associated_data = helper.parse_associated_voucher(invoice)
        associated_period_data = helper.parse_associated_period(invoice)
        opcionals_data = helper.parse_optionals(invoice)

        number = self._get_next_number(ws, data['CbteTipo'], punto_vta)

        _logger.info("Creating pyafipws invoice")
        ws.CrearFactura(
            tipo_cbte=data['CbteTipo'],
            punto_vta=punto_vta,
            fecha_cbte=data['CbteFch'],
            concepto=data['Concepto'],
            tipo_doc=data['DocTipo'],
            nro_doc=data['DocNro'],
            fecha_venc_pago=data['FchVtoPago'],
            moneda_id=data['MonId'],
            moneda_ctz=data['MonCotiz'],
            cancela_misma_mon_ext=data['CanMisMonExt'],
            cond_iva_receptor=data['CondicionIVAReceptorId'],
            fecha_serv_desde=data['FchServDesde'],
            fecha_serv_hasta=data['FchServHasta'],
            cbt_desde=number,
            cbt_hasta=number,
            imp_total=data['total_amount'],
            imp_tot_conc=0.00
            if invoice.denomination == 'c'
            else data['no_taxed_amount'],
            imp_neto=vat_data['base_vat_amount']
            if invoice.denomination != 'c'
            else (data['total_amount'] - tribute_data['tribute_total']),
            imp_iva=vat_data['total_vat_amount'],
            imp_trib=tribute_data['tribute_total'],
            imp_op_ex=data['exempt_amount'],
        )
        _logger.info("Adding vat info")
        for vat_id in vat_data['vat_dict'].keys():
            ws.AgregarIva(
                iva_id=vat_id,
                base_imp=vat_data['vat_dict'][vat_id]['BaseImp'],
                importe=vat_data['vat_dict'][vat_id]['Importe'],
            )
        _logger.info("Adding tributes info")
        for other_tax in tribute_data['tributes_array']:
            ws.AgregarTributo(
                tributo_id=other_tax['Id'],
                desc=other_tax['Desc'],
                base_imp=other_tax['BaseImp'],
                alic=other_tax['Alic'],
                importe=other_tax['Importe'],
            )
        _logger.info("Adding associated invoices info")
        for cbte_asoc in associated_data:
            ws.AgregarCmpAsoc(
                tipo=cbte_asoc['Tipo'],
                pto_vta=cbte_asoc['PtoVta'],
                nro=cbte_asoc['Nro'],
                cuit=cbte_asoc['Cuit'],
                fecha=cbte_asoc['CbteFch'],
            )
        for period_asoc in associated_period_data:
            ws.AgregarPeriodoComprobantesAsociados(
                fecha_desde=period_asoc['from'], fecha_hasta=period_asoc['to']
            )
        _logger.info("Adding optionals info")
        for opt in opcionals_data:
            ws.AgregarOpcional(
                opcional_id=opt['Code'],
                valor=opt['Valor'],
            )
        return {
            'pos_ar': punto_vta,
            'voucher_type': data['CbteTipo'],
            'doctype': data['DocTipo'],
            'docnum': data['DocNro'],
            'voucher_number': number,
            'voucher_date': invoice.invoice_date,
            'amount_total': data['total_amount'],
            'currency': data['MonId'],
            'currency_rate': data['MonCotiz'],
        }

    def send_invoice_to_afip(self, invoice, request_id):
        self.ensure_one()
        if not self.cuit:
            raise UserError(_("Please configure the company VAT!"))

        ws = None
        inv_vals = {}
        req_vals = {
            'invoice_id': invoice.id,
        }
        error_msg = xml_request = ""
        try:
            ws = self.ws_auth()

            req_vals.update(self._set_invoice_in_ws(ws, invoice))

            _logger.info("Trying to push Inovice data to AFIP...")
            ws.CAESolicitar()
            xml_request = ws.XmlRequest
            _logger.info("Data sent to AFIP:")
            _logger.info(xml_request)
        except SoapFault as soap_fault:
            error_msg = "%s: %s" % (
                soap_fault.faultcode,
                soap_fault.faultstring,
            )
            _logger.exception("SOAP Error.")
            _logger.exception(error_msg)
        except Exception as e:
            if ws and ws.Excepcion:
                error_msg = ws.Excepcion
                _logger.exception("WSFE Error.")
                _logger.exception(error_msg)
            else:
                error_msg = str(e)
                _logger.exception("Internal Error.")
                _logger.exception(error_msg)
        finally:
            req_vals.update(
                {
                    'xml_request': xml_request,
                    'result': ws.Resultado,
                    'request_id': request_id,
                }
            )

        helper = WSFEParser()
        try:
            error_msg += '\n'.join(err for err in ws.Errores)
        except Exception as e:
            _logger.info(str(e))

        obs_msg = ''
        try:
            obs_msg = '\n'.join(obs for obs in ws.Observaciones)
        except Exception as e:
            _logger.info(str(e))

        events_msg = ''
        try:
            events_msg = '\n'.join(evn for evn in ws.Eventos)
        except Exception as e:
            _logger.info(str(e))

        cae_due_date, error_msg = helper.get_cae_due_date(ws, error_msg)
        invoice_date, error_msg = helper.get_invoice_date(ws, error_msg)

        if not ws.Resultado or ws.Resultado == "R":
            _logger.warning("AFIP Validation Error. Invoice not approved.")
        else:
            _logger.info("Mission accomplished!")

            inv_name, error_msg = helper.get_invoice_name(
                self.env, req_vals['voucher_type'], ws, error_msg
            )

            inv_vals = {
                'cae': ws.CAE or "",
                'cae_due_date': cae_due_date,
                'internal_number': inv_name,
                'name': inv_name,
                'invoice_date': invoice_date,
            }
            invoice.write(inv_vals)
            _logger.info(
                "Approved\n UPDATED invoice id: %s fields: %s"
                % (invoice.id, inv_vals)
            )
        _logger.info("Transaction with AFIP finished.")

        req_vals.update(
            {
                'errors': error_msg,
                'events': events_msg,
                'observations': obs_msg,
                'cae': ws.CAE or "",
                'cae_due_date': cae_due_date,
            }
        )
        self.env['ws.request.detail'].create(req_vals)
        _logger.info("Request details saved.")
        self.env.cr.commit()  # pylint: disable=invalid-commit

        if error_msg or ws.Resultado != "A":
            raise UserError(error_msg)

        return True
