##############################################################################
#   Copyright (c) 2018 Eynes/E-MIPS (www.eynes.com.ar)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
##############################################################################

from datetime import datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..wsfetools.wsfe_easywsy import WSFE


class WsfeOptionals(models.Model):
    _name = "wsfe.optionals"
    _description = "WSFE Optionals"

    code = fields.Char('Code', required=False, size=4)
    name = fields.Char('Desc', required=True, size=64)
    to_date = fields.Date('Effect Until')
    from_date = fields.Date('Effective From')
    from_afip = fields.Boolean('From AFIP')
    wsfe_config_id = fields.Many2one('wsfe.config', 'WSFE Configuration')


class WsfeTaxCodes(models.Model):
    _name = "wsfe.tax.codes"
    _description = "Tax Codes"

    code = fields.Char('Code', required=False, size=4)
    name = fields.Char('Desc', required=True, size=64)
    to_date = fields.Date('Effect Until')
    from_date = fields.Date('Effective From')
    tax_id = fields.Many2one('account.tax', 'Account Tax')
    wsfe_config_id = fields.Many2one('wsfe.config', 'WSFE Configuration')
    from_afip = fields.Boolean('From AFIP')
    exempt_operations = fields.Boolean(
        'Exempt Operations',
        help='Check it if this VAT Tax corresponds to vat tax exempts '
        + 'operations, such as to sell books, milk, etc. The taxes with this '
        + 'checked, will be reported to AFIP as  exempt operations '
        + '(base amount) without VAT applied on this',
    )


class WsfeConfig(models.Model):
    _name = "wsfe.config"
    _description = "Configuration for WSFE"

    _webservice_class = WSFE

    name = fields.Char('Name', size=64, required=True)
    cuit = fields.Char(related='company_id.partner_id.vat', string='Cuit')
    url = fields.Char('URL for WSFE', size=60, required=True)
    homologation = fields.Boolean(
        'Homologation',
        help="If true, there will be some validations that are disabled, "
        + "for example, invoice number correlativeness",
    )
    point_of_sale_ids = fields.Many2many(
        'account.journal',
        'pos_ar_wsfe_rel',
        'wsfe_config_id',
        'pos_ar_id',
        'Points of Sale',
    )
    vat_tax_ids = fields.One2many(
        'wsfe.tax.codes',
        'wsfe_config_id',
        'Taxes',
        domain=[('from_afip', '=', True)],
    )
    exempt_operations_tax_ids = fields.One2many(
        'wsfe.tax.codes',
        'wsfe_config_id',
        'Taxes of Exempt Operations',
        domain=[('from_afip', '=', False), ('exempt_operations', '=', True)],
    )
    wsaa_ticket_id = fields.Many2one('wsaa.ta', 'Ticket Access')
    company_id = fields.Many2one('res.company', 'Company Name', required=True)
    services_date_difference = fields.Integer(
        'Services and Products', default=10
    )
    products_date_difference = fields.Integer('Products', default=5)
    optional_ids = fields.One2many(
        'wsfe.optionals',
        'wsfe_config_id',
        'Optionals',
        domain=[('from_afip', '=', True)],
    )

    @api.model
    def create(self, vals):

        # Creamos tambien un TA para este servcio y esta compania
        ta_obj = self.env['wsaa.ta']
        wsaa_obj = self.env['wsaa.config']
        service_obj = self.env['afipws.service']

        # Buscamos primero el wsaa que corresponde a esta compania
        # porque hay que recordar que son unicos por compania
        wsaa = wsaa_obj.search([('company_id', '=', vals['company_id'])])
        service = service_obj.search([('name', '=', 'wsfe')])
        if wsaa:
            ta_vals = {
                'name': service.id,
                'company_id': vals['company_id'],
                'config_id': wsaa.id,
            }

            ta = ta_obj.create(ta_vals)
            vals['wsaa_ticket_id'] = ta.id

        return super(WsfeConfig, self).create(vals)

    def unlink(self):
        for wsfe_conf in self:
            wsfe_conf.wsaa_ticket_id.unlink()
        res = super(WsfeConfig, self).unlink()
        return res

    @api.model
    def get_config(self):
        company_id = self.env.context.get('company_id')
        no_raise = self.env.context.get('without_raise', False)
        if not company_id and not no_raise:
            raise UserError(
                _(
                    'Company Error!\n'
                    'There is no company being used by this user'
                )
            )

        ids = self.search([('company_id', '=', company_id)])
        if not ids and not no_raise:
            raise UserError(
                _(
                    'WSFE Config Error!\n'
                    'There is no WSFE configuration set to this company'
                )
            )

        return ids

    @api.model
    def check_errors(self, res, raise_exception=True):
        msg = ''
        if 'errors' in res or 'Errors' in res:
            res_err = res['errors'] if 'errors' in res else res['Errors']
            if isinstance(res_err, list):
                err_array = res_err
                err_var_name = 'msg'
                err_var_code = 'code'
            elif 'Err' in res_err and isinstance(res_err.Err, list):
                err_array = res_err.Err
                err_var_name = 'Msg'
                err_var_code = 'Code'
            errors = [getattr(error, err_var_name) for error in err_array]
            err_codes = [
                str(getattr(error, err_var_code)) for error in err_array
            ]
            msg = ' '.join(errors)
            msg = msg + ' Codigo/s Error:' + ' '.join(err_codes)

            if msg != '' and raise_exception:
                raise UserError(_('WSFE Error!\n') + msg)

        return msg

    def ws_auth(self):
        # TODO This block is repeated, should persist only in WSAA, I think
        token, sign = self.wsaa_ticket_id.get_token_sign()
        auth = {'Token': token, 'Sign': sign, 'Cuit': self.cuit}
        ws = self._webservice_class(self.url)
        ws.login('Auth', auth)
        return ws

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

    def get_afip_tables(self):
        self.ensure_one()
        if not self.cuit:
            raise UserError(
                _("Please configure the company VAT before get Taxes!")
            )
        wsfe_tax_model = self.env['wsfe.tax.codes']
        wsfe_optionals_obj = self.env['wsfe.optionals']

        ws = self.ws_auth()
        data = {'FEParamGetTiposIva': {}}
        ws.add(data, no_check="all")
        response = ws.request('FEParamGetTiposIva')
        err = self.check_errors(response, raise_exception=False)
        if err:
            raise UserError(_("Error reading Taxes!\n") + err)
        for tax in response[0][0]:
            fd = datetime.strptime(tax.FchDesde, '%Y%m%d')
            try:
                td = datetime.strptime(tax.FchHasta, '%Y%m%d')
            except ValueError:
                td = False
            vals = {
                'code': tax.Id,
                'name': tax.Desc,
                'to_date': td,
                'from_date': fd,
                'wsfe_config_id': self.id,
                'from_afip': True,
            }

            # Si no existe el impuesto en la DB, lo creamos de acuerdo a AFIP
            tax = wsfe_tax_model.search(
                [
                    ('code', '=', tax.Id),
                    ('wsfe_config_id', '=', self.id),
                ]
            )
            if not tax:
                wsfe_tax_model.create(vals)

            # Si los codigos estan en la db los modifico
            else:
                tax.write(vals)

        # now optionals
        ws = self.ws_auth()
        data = {'FEParamGetTiposOpcional': {}}
        ws.add(data, no_check="all")
        response = ws.request('FEParamGetTiposOpcional')
        err = self.check_errors(response, raise_exception=False)
        if err:
            raise UserError(_("Error reading Taxes!\n") + err)
        for r in response[0][0]:
            res_c = wsfe_optionals_obj.search(
                [
                    ('code', '=', r.Id),
                    ('wsfe_config_id', '=', self.id),
                ]
            )

            # ~ Si tengo no los codigos de esos Opcionales en la db, los creo
            if not len(res_c):
                fd = datetime.strptime(r.FchDesde, '%Y%m%d')
                try:
                    td = datetime.strptime(r.FchHasta, '%Y%m%d')
                except ValueError:
                    td = False

                wsfe_optionals_obj.create(
                    {
                        'code': r.Id,
                        'name': r.Desc,
                        'to_date': td,
                        'from_date': fd,
                        'wsfe_config_id': self.id,
                        'from_afip': True,
                    }
                )
            # ~ Si los codigos estan en la db los modifico
            else:
                fd = datetime.strptime(r.FchDesde, '%Y%m%d')
                # 'NULL' ?? viene asi de fe_param_get_tipos_iva():
                try:
                    td = datetime.strptime(r.FchHasta, '%Y%m%d')
                except ValueError:
                    td = False

                res_c.write(
                    {
                        'code': r.Id,
                        'name': r.Desc,
                        'to_date': td,
                        'from_date': fd,
                        'wsfe_config_id': self.id,
                        'from_afip': True,
                    }
                )

        return True
