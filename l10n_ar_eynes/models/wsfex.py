##############################################################################
#   Copyright (c) 2018 Eynes/E-MIPS (www.eynes.com.ar)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
##############################################################################

from pyafipws.wsfexv1 import WSFEXv1

from odoo import _, api, fields, models
from odoo.exceptions import UserError


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


class WsfexVoucherTypeCodes(models.Model):
    _name = "wsfex.res.voucher.type.codes"
    _description = "WSFEX Voucher Type Codes"
    _order = 'code'

    code = fields.Integer('Code', required=True)
    name = fields.Char('Desc', required=True, size=64)
    voucher_type_id = fields.Many2one(
        comodel_name='res.voucher.type', string="Odoo Voucher Type"
    )
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
    dst_cuit_ids = fields.One2many(
        comodel_name='dst.cuit.codes',
        inverse_name='wsfex_config_id',
        string='DST CUIT',
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
    voucher_type_ids = fields.One2many(
        comodel_name='wsfex.res.voucher.type.codes',
        inverse_name='wsfex_config_id',
        string='Voucher Type',
    )

    @api.depends('config_id', 'config_id.homologation')
    def _compute_url(self):
        url_prod = self.env.ref('l10n_ar_eynes.url_prod_wsfex').value
        url_homo = self.env.ref('l10n_ar_eynes.url_homo_wsfex').value
        for rec in self:
            rec.url = url_homo if rec.config_id.homologation else url_prod

    def _get_webservice(self):
        return self.env.ref('l10n_ar_eynes.afipws_service_wsfex')

    def get_afip_tables(self):
        self.ensure_one()
        if not self.cuit:
            raise UserError(_("Please configure the company VAT!"))

        # ws = self.ws_auth()

        # error_msg = self._get_currency_tables(ws)
        # error_msg += self._get_optionals_tables(ws)
        # error_msg += self._get_pos_tables(ws)
        # error_msg += self._get_vat_tables(ws)

        # if error_msg:
        #     raise UserError(
        #         _(
        #             """
        #             Error with Webservice
        #             %(error_msg)s
        #             """,
        #             error_msg=error_msg,
        #         )
        #     )

        return True
