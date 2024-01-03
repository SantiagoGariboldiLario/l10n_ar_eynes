##############################################################################
#
#   Copyright (c) 2022-2023 Eynes SRL  (Eynes - Ingenieria del software)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
#
##############################################################################

import logging
import re
from datetime import datetime

from pyafipws.wsaa import WSAA

from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


def clean_url(url):
    """Delete whitespaces and endlines."""
    return re.sub(r'\s+', '', url)


def parse_response_date(date_str):
    """Convert Date format from xml response to Datetime to be saved on Odoo field."""
    exptime_iso = date_str[0 : (date_str.rfind('.') + 4)]
    return datetime.strptime(exptime_iso, '%Y-%m-%dT%H:%M:%S.%f')


class WSAAConfig(models.Model):
    _name = "wsaa.config"
    _description = "Configuration for WSAA"

    certificate = fields.Text('Certificate', readonly=True)
    company_id = fields.Many2one(
        'res.company',
        'Company Name',
        required=True,
        default=lambda self: self.env.user.company_id.id,
    )
    homologation = fields.Boolean(default=True)
    key = fields.Text('Private Key', readonly=True)
    name = fields.Char('Description', size=255)
    url = fields.Char('URL for WSAA', compute='_compute_url', store=True)
    service_ids = fields.One2many(
        'wsaa.ta', 'config_id', string="Authorized Services"
    )

    _sql_constraints = [
        (
            'company_uniq',
            'unique (company_id)',
            'The configuration must be unique per company !',
        )
    ]

    @api.depends('homologation')
    def _compute_url(self):
        url_prod = clean_url(self.env.ref('l10n_ar_eynes.url_prod_wsaa').value)
        url_homo = clean_url(self.env.ref('l10n_ar_eynes.url_homo_wsaa').value)
        for rec in self:
            rec.url = url_homo if rec.homologation else url_prod

    def download_file(self):
        self.ensure_one()
        field = self.env.context.get('field')
        fname = self.env.context.get('filename')
        vals = {
            'model': self._name,
            'field': field,
            'id': self.id,
            'fname': fname,
        }
        action = {
            'type': 'ir.actions.act_url',
            'url': (
                '/web/binary/download_document?model=%(model)s&'
                + 'field=%(field)s&id=%(id)s&filename=%(fname)s'
            )
            % vals,
            'target': 'new',
        }
        return action


class AfipWsService(models.Model):
    _name = "afipws.service"
    _description = "WS Services"

    description = fields.Text('Description')
    name = fields.Char('Service Name', size=30, required=True)

    _sql_constraints = [
        (
            'name_uniq',
            'unique (name)',
            'The name of the service must be unique!',
        )
    ]


class WSAATa(models.Model):
    _name = "wsaa.ta"
    _description = "Ticket Access for WSAA"

    company_id = fields.Many2one('res.company', 'Company Name')
    config_id = fields.Many2one('wsaa.config')
    expiration_time = fields.Char('Expiration Time', size=256)
    name = fields.Many2one('afipws.service', 'Service')
    sign = fields.Text('Sign', readonly=True)
    token = fields.Text('Token', readonly=True)

    _sql_constraints = [
        (
            'company_name_uniq',
            'unique (name, company_id)',
            'The service must be unique per company!',
        )
    ]

    def is_expired(self):
        if not self.expiration_time:
            return True
        expiration_time = datetime.strptime(
            self.expiration_time, '%Y-%m-%d %H:%M:%S.%f'
        )
        return datetime.now() > expiration_time

    def get_token_sign(self):
        """
        Handle AFIP WSAA connection and authentication.
        Returns:
            - sign: str
            - token: str
        """
        CERTIFICATE = self.config_id.certificate
        DEFAULT_TTL = 60 * 60 * 12  # 12 hours (see WSAA documentation)
        FILESTORE_PATH = tools.config.filestore(self.env.cr.dbname)
        FORCE = self._context.get('force_renew', False)
        HOMOLOGATION = self.config_id.homologation
        KEY = self.config_id.key
        SERVICE = self.name.name
        ticket = self
        URL = self.config_id.url

        # create AFIP webservice authentication helper instance:
        wsaa = WSAA()
        wsaa.HOMO = HOMOLOGATION
        # raise python exceptions on any failure
        wsaa.LanzarExcepciones = True
        # Change dir to have read/write permissions
        wsaa.InstallDir = FILESTORE_PATH

        _logger.info("Checking AFIP authentication...")
        if ticket.is_expired() or FORCE:
            try:
                _logger.info(
                    "Access Ticket outdated or do not exists. Creating Access Request Ticket"
                )
                tra = wsaa.CreateTRA(service=SERVICE, ttl=DEFAULT_TTL)
                _logger.info("Encrypting Access Ticket")
                cms = wsaa.SignTRA(tra, CERTIFICATE, KEY)
                _logger.info("Connecting to WebService...")
                wsaa.Conectar(wsdl=URL)
                _logger.info("Login...")
                ta = wsaa.LoginCMS(cms)
                if not ta:
                    _logger.error("Unable to reach Ticket Access.")
                    raise RuntimeError()
                _logger.info("Ticket Access acquired. Saving data.")
                # analyze the access ticket xml and extract the relevant fields
                wsaa.AnalizarXml(xml=ta)
                token = wsaa.ObtenerTagXml("token")
                sign = wsaa.ObtenerTagXml("sign")
                expirationTime = wsaa.ObtenerTagXml("expirationTime")
                # write the access ticket data
                ticket.write(
                    {
                        "expiration_time": parse_response_date(expirationTime),
                        "token": token,
                        "sign": sign,
                    }
                )
                self.env.cr.commit()  # pylint: disable=invalid-commit
            except Exception as e:
                token = sign = None
                if wsaa.Excepcion:
                    # get the exception already parsed by the helper
                    err_msg = wsaa.Excepcion
                    _logger.error("WSAA Error.", err_msg)
                else:
                    err_msg = str(e)
                    _logger.error("Internal Error.", err_msg)
                raise UserError(
                    _("Could not connect. This is the what we received: %s")
                    % (err_msg)
                ) from e

        return ticket.token, ticket.sign

    def action_renew(self):
        """This method is called from button at WSAA, to force the creation of a new TA."""
        self.with_context(force_renew=True).get_token_sign()
        return True
