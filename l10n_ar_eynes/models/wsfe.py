##############################################################################
#   Copyright (c) 2018 Eynes/E-MIPS (www.eynes.com.ar)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
##############################################################################

from datetime import datetime

from pyafipws.wsfev1 import WSFEv1

from odoo import _, api, fields, models
from odoo.exceptions import UserError

SEPARATOR = ";"


def clean_result_date(date):
    if date == 'NULL':
        return False
    return datetime.strptime(date, '%Y%m%d')


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
        comodel_name='ws.pos',
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
        url_prod = self.env.ref('l10n_ar_eynes.url_prod_wsfe').value
        url_homo = self.env.ref('l10n_ar_eynes.url_homo_wsfe').value
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
        self.env['ws.tax.codes'].search(
            [('wsfe_config_id', '=', self.id)]
        ).unlink()
        return super(WsfeConfig, self).unlink()

    def _create_records_from_afip_result(self, ws, result, model_to_create):
        error_msg = ''
        if ws.Excepcion or ws.ErrMsg or ws.Obs:
            error_msg += _(
                """
                %(excep)s
                %(err)s
                %(obs)s
                """,
                excep=ws.Excepcion,
                err=ws.ErrMsg,
                obs=ws.Obs,
            )

        vals_list = []
        for vat_data in result:
            code, name, from_date, to_date = vat_data.split(SEPARATOR)
            vals = {
                'code': code,
                'name': name,
                'from_date': clean_result_date(from_date),
                'to_date': clean_result_date(to_date),
                'from_afip': True,
            }
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
        return error_msg

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
        error_msg = ''
        if ws.Excepcion or ws.ErrMsg or ws.Obs:
            error_msg += _(
                """
                %(excep)s
                %(err)s
                %(obs)s
                """,
                excep=ws.Excepcion,
                err=ws.ErrMsg,
                obs=ws.Obs,
            )

        vals_list = []
        for vat_data in result:
            code, name, blocked, to_date = vat_data.split(SEPARATOR)
            blocked = blocked.split(":")[1]
            to_date = to_date.split(":")[1]
            vals = {
                'code': code,
                'name': name,
                'blocked': False if blocked == 'N' else True,
                'to_date': clean_result_date(to_date),
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

    def get_last_voucher(self, pos, voucher_type):
        self.ensure_one()
        ws = self.ws_auth()
        result = ws.CompUltimoAutorizado(voucher_type, pos)
        # print(result)
        # """
        # if "Errors" in ret:
        #     errores = ret["Errors"]
        #     for error in errores:
        #         self.Errores.append(
        #             "%s: %s"
        #             % (
        #                 error["Err"]["Code"],
        #                 error["Err"]["Msg"],
        #             )
        #         )
        #     self.ErrCode = " ".join([str(error["Err"]["Code"]) for error in errores])
        #     self.ErrMsg = "\n".join(self.Errores)
        # if "Events" in ret:
        #     events = ret["Events"]
        #     self.Eventos = [
        #         "%s: %s" % (evt["Evt"]["Code"], evt["Evt"]["Msg"]) for evt in events
        #     ]
        # """
        return result

    def get_voucher_info(self, pos, voucher_type, number):
        self.ensure_one()
        ws = self.ws_auth()
        result = ws.CompConsultar(voucher_type, pos, number)
        # print(result)
        return result
        # if not hasattr(response, 'ResultGet'):
        #     raise UserError(_("Error fetching voucher from AFIP!"))
        # return response.ResultGet
