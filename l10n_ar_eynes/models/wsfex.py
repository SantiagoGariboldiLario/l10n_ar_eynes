##############################################################################
#   Copyright (c) 2018 Eynes/E-MIPS (www.eynes.com.ar)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
##############################################################################

import logging
from datetime import datetime

from pyafipws.wsfexv1 import WSFEXv1
from pysimplesoap.client import SoapFault

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

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

    @api.constrains('name')
    def _check_name_length(self):
        for rec in self:
            if len(rec.name) != 16:
                raise ValidationError(
                    _(
                        "The export documentation number must have 16 characters."
                    )
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
        comodel_name='ws.pos.line',
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
        url_prod = self.env.ref('l10n_ar_eynes.url_prod_wsfex').value.rstrip()
        url_homo = self.env.ref('l10n_ar_eynes.url_homo_wsfex').value.rstrip()
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
        self.env['ws.pos.line'].search(
            [('wsfex_config_id', '=', self.id)]
        ).unlink()
        self.env['wsfex.uom.codes'].search(
            [('wsfex_config_id', '=', self.id)]
        ).unlink()
        return super(WsfexConfig, self).unlink()

    def _create_records_from_afip_result_no_date(
        self, ws, result, model_to_create
    ):
        helper = WSFEXParser()
        vals_list = []
        for vat_data in result:
            _id, code, name, _void = vat_data.split(SEPARATOR)
            if code and name:
                vals = {
                    'code': code,
                    'name': name,
                }
                record = model_to_create.search(
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
        model_to_create.create(vals_list)
        return helper.parse_errors(ws)

    def _create_records_from_afip_result(self, ws, result, model_to_create):
        helper = WSFEXParser()
        vals_list = []
        for vat_data in result:
            _id, code, name, from_date, to_date, _void = vat_data.split(
                SEPARATOR
            )
            if code and name:
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
        model_to_create.create(vals_list)
        return helper.parse_errors(ws)

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
        vals_list = []
        result = []
        error_msg = ''
        if self.config_id.homologation:
            wsfex_pos = WsPos.search(
                [
                    ('wsfex_config_id', '=', self.id),
                ]
            )
            if not wsfex_pos:
                wsfe_pos = WsPos.search(
                    [
                        ('from_afip', '=', True),
                        ('blocked', '=', False),
                        ('to_date', '=', False),
                    ],
                    order='id desc',
                    limit=1,
                )
                if not wsfe_pos:
                    error_msg = 'There is no HOMO WSFE pos for this company'
                else:
                    vals_list.append(
                        {
                            'code': wsfe_pos.code,
                            'name': wsfe_pos.name,
                            'blocked': wsfe_pos.blocked,
                            'to_date': wsfe_pos.to_date,
                            'from_afip': wsfe_pos.from_afip,
                            'wsfex_config_id': self.id,
                        }
                    )
        else:
            result = ws.GetParamPtosVenta(sep=SEPARATOR)
            for vat_data in result:
                code, blocked, to_date = vat_data.split(SEPARATOR)
                blocked = blocked.split(":")[1]
                to_date = to_date.split(":")[1]
                vals = {
                    'code': code,
                    'name': code,
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
                error_msg = helper.parse_errors(ws)
        WsPos.create(vals_list)
        if len(result) == 0 and not self.config_id.homologation:
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

    def get_voucher_info(self, pos, voucher_type, number):
        _logger.info(
            'Requesting data of voucher %s-%s-%s' % (pos, voucher_type, number)
        )
        self.ensure_one()
        ws = self.ws_auth()
        ws.GetCMP(voucher_type, pos, number)
        helper = WSFEXParser()
        helper.parse_errors_raise(ws, _("get voucher info"))
        ws.AnalizarXml('XmlResponse')
        res = {
            'DocTipo': '80',
            'CbteFch': ws.ObtenerTagXml('Fecha_cbte'),
            'FchVto': ws.ObtenerTagXml('Fch_venc_Cae'),
            'FchProceso': ws.ObtenerTagXml('Fecha_cbte_cae'),
            'DocNro': ws.ObtenerTagXml('Cuit_pais_cliente')
            or ws.ObtenerTagXml('Id_impositivo'),
            'ImpTotal': ws.ObtenerTagXml('Imp_total'),
            'CodAutorizacion': ws.ObtenerTagXml('Cae'),
        }
        _logger.info('Voucher info: %s' % res)
        return res

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

    def _match_invoice_pos(self, invoice):
        ws_pos = self.point_of_sale_ids.search(
            [
                ('journal_id', '=', invoice.journal_id.id),
                ('wsfex_config_id', '=', self.id),
            ],
            order="id desc",
            limit=1,
        )
        if not ws_pos:
            raise UserError(
                _(
                    "This journal '%(journal)s' is not configured in WSFEX.",
                    journal=invoice.journal_id.name,
                )
            )
        return int(ws_pos.code)

    def _set_invoice_in_ws(self, ws, invoice):
        _logger.info("Parsing data from invoice ID: %s" % invoice.id)
        helper = WSFEXParser()
        data = helper.parse_invoice(invoice)
        punto_vta = self._match_invoice_pos(invoice)
        items = helper.parse_items(invoice)
        associated_vouchers = helper.parse_associated_voucher(invoice)
        permissions = helper.parse_permissions(invoice)

        number = self._get_next_number(ws, data['CbteTipo'], punto_vta)

        incoterms = ''
        incoterms_desc = ''
        if invoice.invoice_incoterm_id:
            inv_incoterms = self.env['wsfex.incoterms.codes'].search(
                [
                    ('incoterms_id', '=', invoice.invoice_incoterm_id.id),
                    ('wsfex_config_id', '=', self.id),
                ]
            )
            if not inv_incoterms:
                raise UserError(
                    _(
                        "Incoterm %(name)s is not configured in WSFEX.",
                        name=invoice.invoice_incoterm_id.display_name,
                    )
                )
            incoterms = inv_incoterms.code
            incoterms_desc = inv_incoterms.name

        _logger.info("Creating pyafipws invoice")
        ws.CrearFactura(
            tipo_cbte=data['CbteTipo'],
            punto_vta=punto_vta,
            cbte_nro=number,
            fecha_cbte=data['CbteFch'],
            imp_total=data['total_amount'],
            tipo_expo=data['expo_type'],
            permiso_existente=data['exist_perm'],
            pais_dst_cmp=data['pais_dst'],
            nombre_cliente=data['partner_name'],
            cuit_pais_cliente=data['cuit_pais'],
            domicilio_cliente=data['partner_address'],
            id_impositivo=data['partner_cuit'],
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
        return {
            'pos_ar': punto_vta,
            'voucher_type': data['CbteTipo'],
            'docnum': data['DocNro'] or data['cuit_pais'],
            'voucher_number': number,
            'voucher_date': invoice.invoice_date,
            # 'amount_total': data['total_amount'], This field doesn't exist in WSFEX request
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
        error_msg = ""
        try:
            ws = self.ws_auth()

            req_vals.update(self._set_invoice_in_ws(ws, invoice))

            _logger.info("Trying to push Inovice data to AFIP...")
            afip_id = self._get_next_id(ws)
            ws.Authorize(afip_id)
            xml_request = ws.XmlRequest
            _logger.info("Data sent to AFIP:")
            _logger.info(xml_request)
            req_vals.update({'xml_request': xml_request})
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
                    'request_id': request_id,
                }
            )

        if error_msg:
            req_vals.update(
                {
                    'result': 'E',
                    'errors': error_msg,
                }
            )
        else:
            error_msg = '' if '0: ok' in ws.ErrMsg.lower() else ws.ErrMsg
            obs_msg = '' if '0: ok' in ws.Obs.lower() else ws.Obs
            events_msg = ''
            for event in ws.Eventos:
                events_msg += '' if '0: ok' in event.lower() else event
            if ws.Resultado in ["A"] or ws.CAE:
                _logger.info("Mission accomplished!")
                cae_due_date = (
                    ws.Vencimiento
                    and datetime.strptime(ws.Vencimiento, "%d/%m/%Y").date()
                    or False
                )
                req_vals.update(
                    {
                        'result': ws.Resultado,
                        'errors': error_msg,
                        'events': events_msg,
                        'observations': obs_msg,
                        'cae': ws.CAE or "",
                        'cae_due_date': cae_due_date,
                    }
                )

                inv_name = "%s-%s" % (
                    str(req_vals['pos_ar']).zfill(5),
                    str(ws.CbteNro).zfill(8),
                )
                inv_vals = {
                    'cae': ws.CAE,
                    'cae_due_date': cae_due_date,
                    'internal_number': inv_name,
                    'name': inv_name,
                }
                invoice.write(inv_vals)
                _logger.info(
                    "Approved\n UPDATED invoice fields: %s" % (inv_vals)
                )
            else:
                _logger.warning("AFIP Validation Error. Invoice not approved.")
                req_vals.update(
                    {
                        'result': 'E',
                        'errors': error_msg,
                        'events': events_msg,
                        'observations': obs_msg,
                    }
                )
            _logger.info("Transaction with AFIP finished.")

        self.env['ws.request.detail'].create(req_vals)
        _logger.info("Request details saved.")
        self.env.cr.commit()  # pylint: disable=invalid-commit

        if error_msg or ws.Resultado != "A":
            raise UserError(error_msg)

        return True
