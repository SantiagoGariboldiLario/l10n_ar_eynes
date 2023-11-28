##############################################################################
#   Copyright (c) 2018 Eynes/E-MIPS (www.eynes.com.ar)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
##############################################################################

import logging
from datetime import datetime

from pyafipws.wsfexv1 import WSFEXv1
from pysimplesoap.client import SoapFault

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..wsfetools.wsfex_helper import WSFEXParser

_logger = logging.getLogger(__name__)

SEPARATOR = ";"


class AccountIncoterms(models.Model):
    _name = 'account.incoterms'
    _inherit = 'account.incoterms'

    def name_get(self):
        res = []
        for inc in self:
            name_lst = []
            if inc.code:
                name_lst.append("[%s]" % inc.code)
            name_lst.append(inc.name)
            name = (" ").join(name_lst)
            res.append((inc.id, name))
        return res


class WsfexShippingPermission(models.Model):
    _name = "wsfex.shipping.permission"
    _description = "WSFEX Shipping Permission"

    name = fields.Char('Code', required=True, size=16)
    invoice_id = fields.Many2one('account.move', 'Invoice')
    dst_country_id = fields.Many2one(
        'wsfex.dst.country.codes', 'Dest Country', required=True
    )


class WsfexUomCodes(models.Model):
    _name = "wsfex.uom.codes"
    _description = "WSFEX UoM Codes"
    _order = 'code'

    code = fields.Integer('Code', required=True)
    name = fields.Char('Desc', required=True, size=64)
    uom_id = fields.Many2one('uom.uom', string="Odoo UoM")
    wsfex_config_id = fields.Many2one('wsfex.config')


class WsfexLangCodes(models.Model):
    _name = "wsfex.lang.codes"
    _description = "WSFEX Language Codes"
    _order = 'code'

    code = fields.Integer('Code', required=True)
    name = fields.Char('Desc', required=True, size=64)
    lang_id = fields.Many2one('res.lang', string="Odoo Language")
    wsfex_config_id = fields.Many2one('wsfex.config')


class WsfexDstCountryCodes(models.Model):
    _name = "wsfex.dst.country.codes"
    _description = "WSFEX Dest Country Codes"
    _order = 'name'

    code = fields.Char('Code', size=3, required=True)
    name = fields.Char('Desc', required=True, size=64)
    country_id = fields.Many2one('res.country', string="Odoo Country")
    wsfex_config_id = fields.Many2one('wsfex.config')


class WsfexIncotermsCodes(models.Model):
    _name = "wsfex.incoterms.codes"
    _description = "WSFEX Incoterms Codes"
    _order = 'code'

    code = fields.Char('Code', size=5, required=True)
    name = fields.Char('Desc', required=True, size=64)
    incoterms_id = fields.Many2one(
        comodel_name='account.incoterms', string="Odoo Incoterm"
    )
    wsfex_config_id = fields.Many2one('wsfex.config')


class WsfexExportTypeCodes(models.Model):
    _name = "wsfex.export.type.codes"
    _description = "WSFEX Export Type Codes"
    _order = 'code'

    code = fields.Integer('Code', required=True)
    name = fields.Char('Desc', required=True, size=64)
    wsfex_config_id = fields.Many2one('wsfex.config')


class WsfexConfig(models.Model):
    _name = "wsfex.config"
    _inherit = "ws.config"
    _description = "Configuration for WSFEX"

    _webservice_class = WSFEXv1

    currency_ids = fields.One2many(
        comodel_name='ws.currency.codes',
        inverse_name='wsfex_config_id',
        string='Currencies',
        domain=[('from_afip', '=', True)],
    )
    country_ids = fields.One2many(
        comodel_name='wsfex.dst.country.codes',
        inverse_name='wsfex_config_id',
        string='Countries',
    )
    export_type_ids = fields.One2many(
        comodel_name='wsfex.export.type.codes',
        inverse_name='wsfex_config_id',
        string='Export Type',
    )
    incoterms_ids = fields.One2many(
        comodel_name='wsfex.incoterms.codes',
        inverse_name='wsfex_config_id',
        string='Incoterms',
    )
    lang_ids = fields.One2many(
        comodel_name='wsfex.lang.codes',
        inverse_name='wsfex_config_id',
        string='Languages',
    )
    point_of_sale_ids = fields.One2many(
        comodel_name='ws.pos',
        inverse_name='wsfex_config_id',
        string='POS',
        domain=[('from_afip', '=', True)],
    )
    uom_ids = fields.One2many(
        comodel_name='wsfex.uom.codes',
        inverse_name='wsfex_config_id',
        string='Units of Measure',
    )

    @api.depends('config_id', 'config_id.homologation')
    def _compute_url(self):
        url_prod = self.env.ref('l10n_ar_eynes.url_prod_wsfex').value
        url_homo = self.env.ref('l10n_ar_eynes.url_homo_wsfex').value
        for rec in self:
            rec.url = url_homo if rec.config_id.homologation else url_prod

    def _get_webservice(self):
        return self.env.ref('l10n_ar_eynes.afipws_service_wsfex')

    def unlink(self):
        self.env['ws.currency.codes'].search(
            [('wsfex_config_id', '=', self.id)]
        ).unlink()
        self.env['wsfex.dst.country.codes'].search(
            [('wsfex_config_id', '=', self.id)]
        ).unlink()
        self.env['wsfex.export.type.codes'].search(
            [('wsfex_config_id', '=', self.id)]
        ).unlink()
        self.env['wsfex.incoterms.codes'].search(
            [('wsfex_config_id', '=', self.id)]
        ).unlink()
        self.env['wsfex.lang.codes'].search(
            [('wsfex_config_id', '=', self.id)]
        ).unlink()
        self.env['ws.pos'].search([('wsfex_config_id', '=', self.id)]).unlink()
        self.env['wsfex.uom.codes'].search(
            [('wsfex_config_id', '=', self.id)]
        ).unlink()
        self.env['wsfex.res.voucher.type.codes'].search(
            [('wsfex_config_id', '=', self.id)]
        ).unlink()
        return super(WsfexConfig, self).unlink()

    def _get_currency_tables(self, ws):
        WsCurrencyCodes = self.env['ws.currency.codes']
        result = ws.GetParamMon(sep=SEPARATOR)
        error_msg = self._create_records_from_afip_result(
            ws, result, WsCurrencyCodes
        )
        if error_msg:
            error_msg = 'Error getting Currency tables. Response:\n' + error_msg
        return error_msg

    def _get_countries_tables(self, ws):
        WsfexCountries = self.env['wsfex.dst.country.codes']
        result = ws.GetParamDstPais(sep=SEPARATOR)
        error_msg = self._create_records_from_afip_result_no_date(
            ws=ws, result=result, model_to_create=WsfexCountries
        )
        if error_msg:
            error_msg = (
                'Error getting Countries tables. Response:\n' + error_msg
            )
        return error_msg

    def _get_lang_tables(self, ws):
        WsfexLang = self.env['wsfex.lang.codes']
        result = ws.GetParamIdiomas(sep=SEPARATOR)
        error_msg = self._create_records_from_afip_result(ws, result, WsfexLang)
        if error_msg:
            error_msg = (
                'Error getting Languages tables. Response:\n' + error_msg
            )
        return error_msg

    def _get_export_type_tables(self, ws):
        WsfexExportType = self.env['wsfex.export.type.codes']
        result = ws.GetParamTipoExpo(sep=SEPARATOR)
        error_msg = self._create_records_from_afip_result(
            ws, result, WsfexExportType
        )
        if error_msg:
            error_msg = (
                'Error getting Export Type tables. Response:\n' + error_msg
            )
        return error_msg

    def _get_UOM_tables(self, ws):
        WsfexUOM = self.env['wsfex.uom.codes']
        result = ws.GetParamUMed(sep=SEPARATOR)
        error_msg = self._create_records_from_afip_result(ws, result, WsfexUOM)
        if error_msg:
            error_msg = 'Error getting UOM tables. Response:\n' + error_msg
        return error_msg

    def _get_incoterms_tables(self, ws):
        WsfexIncoterms = self.env['wsfex.incoterms.codes']
        result = ws.GetParamIncoterms(sep=SEPARATOR)
        error_msg = self._create_records_from_afip_result(
            ws, result, WsfexIncoterms
        )
        if error_msg:
            error_msg = (
                'Error getting Incoterms tables. Response:\n' + error_msg
            )
        return error_msg

    def _get_pos_tables(self, ws):
        WsPos = self.env['ws.pos']
        helper = WSFEXParser()
        result = ws.GetParamPtosVenta(sep=SEPARATOR)
        vals_list = []
        for vat_data in result:
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
                    ('wsfex_config_id', '=', self.id),
                ]
            )
            if not record:
                vals.update(
                    {
                        'wsfex_config_id': self.id,
                    }
                )
                vals_list.append(vals)
            else:
                record.write(vals)
        WsPos.create(vals_list)
        error_msg = helper.parse_errors(ws)
        if len(result) == 0:
            error_msg = (
                _("Error: this company doesn't have POS for this Webservice.\n")
                + error_msg
            )
        if error_msg:
            error_msg = 'Error getting POS tables. Response:\n' + error_msg
        return error_msg

    def get_afip_tables(self):
        self.ensure_one()
        if not self.cuit:
            raise UserError(_("Please configure the company VAT!"))

        ws = self.ws_auth()

        error_msg = self._get_pos_tables(ws)
        error_msg += self._get_currency_tables(ws)
        error_msg += self._get_countries_tables(ws)
        error_msg += self._get_lang_tables(ws)
        error_msg += self._get_export_type_tables(ws)
        error_msg += self._get_UOM_tables(ws)
        error_msg += self._get_incoterms_tables(ws)

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

    def _get_next_id(self, ws):
        _logger.info("Checking last ID informed to AFIP")
        last_id = ws.GetLastID()
        helper = WSFEXParser()
        helper.parse_errors_raise(ws, _("get the last ID informed"))
        return int(last_id) + 1

    def _get_next_number(self, ws, tipo_cbte, pto_vta):
        _logger.info(
            "Checking last voucher informed to AFIP - Type: %s, POS: %s"
            % (tipo_cbte, pto_vta)
        )
        last_voucher_number = ws.GetLastCMP(tipo_cbte, pto_vta)
        helper = WSFEXParser()
        helper.parse_errors_raise(ws, _("get the last voucher informed"))
        return int(last_voucher_number) + 1

    def _set_invoice_in_ws(self, ws, invoice):
        _logger.info("Parsing data from invoice ID: %s" % invoice.id)
        helper = WSFEXParser()
        data = helper.parse_invoice(invoice)
        items = helper.parse_items(invoice)
        associated_vouchers = helper.parse_associated_voucher(invoice)
        permissions = helper.parse_permissions(invoice)

        number = self._get_next_number(ws, data['CbteTipo'], data['PtoVta'])

        incoterms = ''
        incoterms_desc = None
        inv_incoterms = self.env['wsfex.incoterms.codes'].search(
            [
                ('incoterms_id', '=', invoice.invoice_incoterm_id.id),
                ('wsfex_config_id', '=', self.id),
            ]
        )
        if inv_incoterms:
            incoterms = inv_incoterms.code
            incoterms_desc = inv_incoterms.name

        _logger.info("Creating pyafipws invoice")
        ws.CrearFactura(
            tipo_cbte=data['CbteTipo'],
            punto_vta=data['PtoVta'],
            cbte_nro=number,
            fecha_cbte=data['CbteFch'],
            imp_total=data['total_amount'],
            tipo_expo=data['expo_type'],
            permiso_existente=data['exist_perm'],
            pais_dst_cmp=data['pais_dst'],
            nombre_cliente=data['partner_name'],
            cuit_pais_cliente=data['cuit_pais'],
            domicilio_cliente=data['partner_address'],
            id_impositivo=data['DocNro'],
            moneda_id=data['MonId'],
            moneda_ctz=data['MonCotiz'],
            # obs_comerciales="",
            # obs_generales="",
            # forma_pago="",
            idioma_cbte=data['lang'],
            incoterms=incoterms,
            incoterms_ds=incoterms_desc,
            fecha_pago=data['FchVtoPago'],
        )
        _logger.info("Adding item info")
        for item in items:
            ws.AgregarItem(
                codigo=item['Pro_codigo'],
                ds=item['Pro_ds'],
                qty=item['Pro_qty'],
                umed=item['Pro_umed'],
                precio=item['Pro_precio_uni'],
                importe=item['Pro_total_item'],
                bonif=item['Pro_bonificacion'],
            )
        _logger.info("Adding permission info")
        for permission in permissions:
            ws.AgregarPermiso(
                id_permiso=permission['id'],
                dst_merc=permission['dest'],
            )
        _logger.info("Adding associated invoices info")
        for cbte_asoc in associated_vouchers:
            ws.AgregarCmpAsoc(
                cbte_tipo=cbte_asoc['Tipo'],
                cbte_punto_vta=cbte_asoc['PtoVta'],
                cbte_nro=cbte_asoc['Nro'],
                cbte_cuit=cbte_asoc['Cuit'],
            )

    def send_invoices_to_afip(self, invoices):
        self.ensure_one()
        if not self.cuit:
            raise UserError(_("Please configure the company VAT!"))

        ws = self.ws_auth()

        WsRequest = self.env['ws.request']
        WsRequestDetail = self.env['ws.request.detail']
        request = WsRequest.create({'date_request': fields.Datetime.today()})
        qty_processed = 0
        for invoice in invoices:
            self._set_invoice_in_ws(ws, invoice)

            _logger.info("Trying to push Inovice data to AFIP...")
            error_msg = ""
            try:
                qty_processed += 1
                afip_id = self._get_next_id(ws)
                ws.Authorize(afip_id)
            except SoapFault as soap_fault:
                error_msg = "%s: %s" % (
                    soap_fault.faultcode,
                    soap_fault.faultstring,
                )
                _logger.error("SOAP Error.", error_msg)
            except Exception as e:
                if ws.Excepcion:
                    error_msg = ws.Excepcion
                    _logger.error("WSFE Error.", error_msg)
                else:
                    error_msg = str(e)
                    _logger.error("Internal Error.", error_msg)
            if error_msg:
                WsRequestDetail.create(
                    {
                        'invoice_id': invoice.id,
                        'result': 'E',
                        'errors': error_msg,
                        'request_id': request.id,
                    }
                )
                _logger.info("Request details saved.")
                self.env.cr.commit()  # pylint: disable=invalid-commit
                raise UserError(
                    _("Error trying to validate Electronic Invoice: %s")
                    % (error_msg)
                )
            error_msg = '\n'.join(err for err in ws.Errores)
            events_msg = '\n'.join(evn for evn in ws.Eventos)
            obs_msg = '\n'.join(obs for obs in ws.Observaciones)
            if ws.Resultado == "R":
                _logger.warning("AFIP Validation Error. Invoice not approved.")
                WsRequestDetail.create(
                    {
                        'invoice_id': invoice.id,
                        'result': 'E',
                        'errors': error_msg,
                        'events': events_msg,
                        'observations': obs_msg,
                        'request_id': request.id,
                    }
                )
                _logger.info("Request details saved.")
                self.env.cr.commit()  # pylint: disable=invalid-commit
                raise UserError(
                    _(
                        """
                        Error trying to validate Electronic Invoice: %s
                        Please, check WS Request generated. You will find the result of
                        current transaction there.
                        """
                    )
                    % (invoice.id)
                )

            else:
                _logger.info("Mission accomplished!")
                WsRequestDetail.create(
                    {
                        'invoice_id': invoice.id,
                        'request_id': request.id,
                        'result': ws.Resultado,
                        'errors': error_msg,
                        'events': events_msg,
                        'observations': obs_msg,
                        'cae': ws.CAE or "",
                        'cae_due_date': ws.Vencimiento
                        and datetime.strptime(ws.Vencimiento, "%Y%m%d").date()
                        or False,
                    }
                )
                self.env.cr.commit()  # pylint: disable=invalid-commit
                _logger.info("Request details saved.")

                inv_name = "%s-%s" % (
                    str(ws.PuntoVenta).zfill(5),
                    str(ws.CbteNro).zfill(8),
                )
                inv_vals = {
                    'cae': ws.CAE,
                    'cae_due_date': datetime.strptime(
                        ws.Vencimiento, "%Y%m%d"
                    ).date(),
                    'internal_number': inv_name,
                    'name': inv_name,
                    'invoice_date': datetime.strptime(
                        ws.FechaCbte, "%Y%m%d"
                    ).date(),
                }
                invoice.write(inv_vals)
                _logger.info(
                    "CAE: %s. Result: %s\n UPDATED invoice fields: %s"
                    % (ws.CAE, ws.Resultado, inv_vals)
                )
                self.env.cr.commit()  # pylint: disable=invalid-commit

        _logger.info("Transaction with AFIP finished.")

        return True
