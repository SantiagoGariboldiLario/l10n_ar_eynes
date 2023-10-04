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

    vat_tax_ids = fields.One2many(
        'ws.tax.codes',
        'wsfe_config_id',
        'Taxes',
        domain=[('from_afip', '=', True)],
    )
    exempt_operations_tax_ids = fields.One2many(
        'ws.tax.codes',
        'wsfe_config_id',
        'Taxes of Exempt Operations',
        domain=[('from_afip', '=', False), ('exempt_operations', '=', True)],
    )
    optional_ids = fields.One2many(
        'ws.optionals',
        'wsfe_config_id',
        'Optionals',
        domain=[('from_afip', '=', True)],
    )
    point_of_sale_ids = fields.One2many(
        'ws.pos',
        'wsfe_config_id',
        'POS',
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
        self.env['ws.tax.codes'].search(
            [('wsfe_config_id', '=', self.id)]
        ).unlink()
        self.env['ws.optionals'].search(
            [('wsfe_config_id', '=', self.id)]
        ).unlink()
        self.env['ws.pos'].search([('wsfe_config_id', '=', self.id)]).unlink()
        return super(WsfeConfig, self).unlink()

    def get_last_voucher(self, pos, voucher_type):
        self.ensure_one()
        ws = self.ws_auth()
        data = {
            'FECompUltimoAutorizado': {
                'CbteTipo': voucher_type,
                'PtoVta': pos,
            }
        }
        ws.add(data)
        response = ws.request('FECompUltimoAutorizado')
        res = ws.parse_response(response)
        del ws
        last = res['response'].CbteNro
        return last

    def get_voucher_info(self, pos, voucher_type, number):
        self.ensure_one()
        ws = self.ws_auth()
        data = {
            'FECompConsultar': {
                'FeCompConsReq': {
                    'CbteTipo': voucher_type,
                    'CbteNro': number,
                    'PtoVta': pos,
                }
            }
        }
        ws.add(data)
        response = ws.request('FECompConsultar')
        if not hasattr(response, 'ResultGet'):
            raise UserError(_("Error fetching voucher from AFIP!"))
        return response.ResultGet

    def _get_vat_tables(self, ws):
        WsTaxCodes = self.env['ws.tax.codes']

        result = ws.ParamGetTiposIva(sep=SEPARATOR)

        error_msg = ''
        if ws.Excepcion or ws.ErrMsg or ws.Obs:
            error_msg += _(
                """ParamGetTiposIva raise:
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
            tax = WsTaxCodes.search(
                [
                    ('code', '=', code),
                    ('wsfe_config_id', '=', self.id),
                ]
            )
            if not tax:
                vals.update(
                    {
                        'wsfe_config_id': self.id,
                    }
                )
                vals_list.append(vals)
            else:
                tax.write(vals)
        WsTaxCodes.create(vals_list)
        return error_msg

    def get_afip_tables(self):
        self.ensure_one()
        if not self.cuit:
            raise UserError(_("Please configure the company VAT!"))

        ws = self.ws_auth()

        error_msg = self._get_vat_tables(ws)

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
