##############################################################################
#   Copyright (c) 2018 Eynes/E-MIPS (www.eynes.com.ar)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
##############################################################################

import logging

from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

SEPARATOR = ";"


class WsCurrencyCodes(models.Model):
    _name = "ws.currency.codes"
    _description = "WS Currency Codes"
    _order = 'code'

    code = fields.Char('Code', required=True, size=4)
    currency_id = fields.Many2one(
        comodel_name='res.currency', string="Odoo Currency"
    )
    from_afip = fields.Boolean('From AFIP')
    from_date = fields.Date('Effective From')
    name = fields.Char('Desc', required=True, size=64)
    to_date = fields.Date('Effect Until')
    wsfe_config_id = fields.Many2one(
        comodel_name='wsfe.config', string='WebService WSFE'
    )
    wsfex_config_id = fields.Many2one(
        comodel_name='wsfex.config', string='WebService WSFEX'
    )

    @api.constrains('wsfe_config_id', 'wsfex_config_id')
    def _check_only_one_ws_associated(self):
        if self.wsfe_config_id and self.wsfex_config_id:
            raise ValidationError(
                _(
                    """
                    This table must be related with only one Webservice.
                    """
                )
            )


class WsOptionals(models.Model):
    _name = "ws.optionals"
    _description = "Optionals"

    code = fields.Char('Code', required=False, size=4)
    from_afip = fields.Boolean('From AFIP')
    from_date = fields.Date('Effective From')
    name = fields.Char('Desc', required=True, size=64)
    to_date = fields.Date('Effect Until')
    wsfe_config_id = fields.Many2one(
        comodel_name='wsfe.config', string='WebService WSFE'
    )
    wsfex_config_id = fields.Many2one(
        comodel_name='wsfex.config', string='WebService WSFEX'
    )

    @api.constrains('wsfe_config_id', 'wsfex_config_id')
    def _check_only_one_ws_associated(self):
        if self.wsfe_config_id and self.wsfex_config_id:
            raise ValidationError(
                _(
                    """
                    This table must be related with only one Webservice.
                    """
                )
            )


class WsPOS(models.Model):
    _name = "ws.pos"
    _description = "POS"

    code = fields.Char('AFIP POS', required=True, size=4)
    blocked = fields.Boolean()
    from_afip = fields.Boolean('From AFIP')
    name = fields.Char('Desc', required=True, size=64)
    priority = fields.Integer()
    to_date = fields.Date('Effect Until')
    wsfe_config_id = fields.Many2one(
        comodel_name='wsfe.config', string='WebService WSFE'
    )
    wsfex_config_id = fields.Many2one(
        comodel_name='wsfex.config', string='WebService WSFEX'
    )

    @api.constrains('wsfe_config_id', 'wsfex_config_id')
    def _check_only_one_ws_associated(self):
        if self.wsfe_config_id and self.wsfex_config_id:
            raise ValidationError(
                _(
                    """
                    This table must be related with only one Webservice.
                    """
                )
            )


class WsPOSLine(models.Model):
    _inherit = "ws.pos"
    _name = "ws.pos.line"
    _description = "POS line for WS configuration"

    code = fields.Char(related='pos_id.code')
    blocked = fields.Boolean(related='pos_id.blocked')
    from_afip = fields.Boolean(related='pos_id.from_afip')
    journal_id = fields.Many2one(
        comodel_name='account.journal',
        domain=[('type', '=', 'sale')],
        string='Odoo POS',
    )
    name = fields.Char(related='pos_id.name')
    pos_id = fields.Many2one(
        comodel_name='ws.pos',
        string='AFIP POS',
    )
    priority = fields.Integer(related='pos_id.priority')
    to_date = fields.Date(related='pos_id.to_date')
    wsfe_config_id = fields.Many2one(
        comodel_name='wsfe.config', related='pos_id.wsfe_config_id'
    )
    wsfex_config_id = fields.Many2one(
        comodel_name='wsfex.config', related='pos_id.wsfex_config_id'
    )

    @api.model
    def write(self, vals):
        if self.journal_id:
            self.journal_id.fiscal_type = 'internal'
        journal_id = vals.get('journal_id', None)
        if journal_id:
            journal = self.env['account.journal'].browse(journal_id)
            journal.fiscal_type = 'electronic'
        return super(WsPOSLine, self).write(vals)

    @api.model
    def create(self, vals):
        journal_id = vals.get('journal_id', None)
        if journal_id:
            journal = self.env['account.journal'].browse(journal_id)
            journal.fiscal_type = 'electronic'
        return super(WsPOSLine, self).create(vals)

    def unlink(self):
        if self.journal_id:
            self.journal_id.fiscal_type = 'internal'
        return super(WsPOSLine, self).unlink()


class WsTaxCodes(models.Model):
    _name = "ws.tax.codes"
    _description = "Tax Codes"

    code = fields.Char('Code', required=False, size=4)
    exempt_operations = fields.Boolean(
        string='Exempt Operations',
        help='Check it if this VAT Tax corresponds to vat tax exempts '
        + 'operations, such as to sell books, milk, etc. The taxes with this '
        + 'checked, will be reported to AFIP as  exempt operations '
        + '(base amount) without VAT applied on this',
    )
    from_afip = fields.Boolean('From AFIP')
    from_date = fields.Date('Effective From')
    name = fields.Char('Desc', required=True, size=64)
    tax_id = fields.Many2one(
        comodel_name='account.tax',
        string='Odoo Account Tax',
        domain=[
            ('type_tax_use', '=', 'sale'),
            ('tax_group_id.name', 'ilike', 'vat'),
        ],
    )
    to_date = fields.Date('Effect Until')
    wsfe_config_id = fields.Many2one(
        comodel_name='wsfe.config', string='WebService WSFE'
    )
    wsfex_config_id = fields.Many2one(
        comodel_name='wsfex.config', string='WebService WSFEX'
    )

    @api.constrains('wsfe_config_id', 'wsfex_config_id')
    def _check_only_one_ws_associated(self):
        if self.wsfe_config_id and self.wsfex_config_id:
            raise ValidationError(
                _(
                    """
                    This table must be related with only one Webservice.
                    """
                )
            )


class WsConfig(models.Model):
    _name = "ws.config"
    _description = "General structure of configuration for AFIP WebService"

    _webservice_class = None

    company_id = fields.Many2one('res.company', 'Company Name', required=True)
    config_id = fields.Many2one('wsaa.config')
    cuit = fields.Char(related='company_id.partner_id.vat', string='Cuit')
    name = fields.Char('Name', size=64, required=True)
    url = fields.Char('URL for WS', compute="_compute_url")
    wsaa_ticket_id = fields.Many2one('wsaa.ta', 'Ticket Access')

    products_date_difference = fields.Integer(
        'Products',
        default=5,
        help="""
        This is the maximum date range that an invoice can be created before
        or after the validation date.
        """,
    )
    services_date_difference = fields.Integer(
        'Services and Products',
        default=10,
        help="""
        This is the maximum date range that an invoice can be created before
        or after the validation date.
        """,
    )

    @api.depends('config_id', 'config_id.homologation')
    def _compute_url(self):
        """To be inherited. Using the self.env.ref() to the URLs"""
        url_prod = 'https://'
        url_homo = 'https://'
        for rec in self:
            rec.url = url_homo if rec.config_id.homologation else url_prod

    def _get_webservice(self):
        """To be inherited. Returns the self.env.ref() of the Webservice."""
        return ""

    @api.model
    def create(self, vals):
        """
        Create Ticket Access for the Webservice at the same time it is created.
        """
        WSAATa = self.env['wsaa.ta']
        WSAAConfig = self.env['wsaa.config']
        service = self._get_webservice()

        if not service:
            raise UserError(_("Webservice not implemented."))

        # WSAA are unique per company. Search the WSAA for current company:
        wsaa = WSAAConfig.search([('company_id', '=', vals['company_id'])])
        if wsaa:
            # Create a TA for this service and company:
            ta_vals = {
                'name': service.id,
                'company_id': vals['company_id'],
                'config_id': wsaa.id,
            }
            ta = WSAATa.create(ta_vals)

            vals.update(
                {
                    'wsaa_ticket_id': ta.id,
                    'config_id': wsaa.id,
                }
            )
        else:
            # If not WSAA configuration has found, we need to alert user to do it.
            company_name = (
                self.env['res.company'].browse(vals['company_id']).name
            )
            raise UserError(
                _(
                    """
                        Current company %(company_name)s doesn't have WSAA configured.
                        Please, go to Configuration --> WSAA configuration
                    """,
                    company_name=company_name,
                )
            )

        return super(WsConfig, self).create(vals)

    def unlink(self):
        for ws_conf in self:
            ws_conf.wsaa_ticket_id.unlink()
        return super(WsConfig, self).unlink()

    @api.model
    def get_config(self):
        """"""
        company_id = self.env.context.get('company_id')
        if not company_id:
            raise UserError(
                _(
                    """
                        Company Error!
                    There is no company being used by this user
                    """
                )
            )

        config = self.search([('company_id', '=', company_id)])
        if not config:
            service = self._get_webservice()
            raise UserError(
                _(
                    """
                    WS Configuration Error!
                    There is no %(ws_name)s configuration set to this company.
                    """,
                    ws_name=service.name if service else 'WS',
                )
            )

        return config

    def ws_auth(self):
        token, sign = self.wsaa_ticket_id.get_token_sign()
        FILESTORE_PATH = tools.config.filestore(self.env.cr.dbname)

        ws = self._webservice_class()
        if not ws:
            raise UserError(_("Webservice not implemented."))

        ws.HOMO = self.config_id.homologation
        ws.InstallDir = FILESTORE_PATH

        _logger.info("Starting connection with AFIP...")
        ws.Conectar("", self.url, "", cacert=True)
        _logger.info("Webservice succesfully connected.")

        ws.Cuit = self.company_id.vat
        ws.Token = token
        ws.Sign = sign

        return ws
