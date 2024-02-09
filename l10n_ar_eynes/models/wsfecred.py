##############################################################################
#   Copyright (c) 2018 Eynes/E-MIPS (www.eynes.com.ar)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
##############################################################################

import logging

from pyafipws.wsfecred import WSFECred
from pysimplesoap.client import SoapFault

from odoo import _, api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

SEPARATOR = ';'


class WsfeConfig(models.Model):
    _name = 'wsfecred.config'
    _inherit = 'ws.config'
    _description = 'Configuration for WSFECRED'

    _webservice_class = WSFECred

    @api.depends('config_id', 'config_id.homologation')
    def _compute_url(self):
        url_prod = self.env.ref(
            'l10n_ar_eynes.url_prod_wsfecred'
        ).value.rstrip()
        url_homo = self.env.ref(
            'l10n_ar_eynes.url_homo_wsfecred'
        ).value.rstrip()
        for rec in self:
            rec.url = url_homo if rec.config_id.homologation else url_prod

    def _get_webservice(self):
        return self.env.ref('l10n_ar_eynes.afipws_service_wsfecred')

    def check_partner_obliged_to_FCE(self, invoice):
        self.ensure_one()
        if not self.cuit:
            raise UserError(_('Please configure the company VAT!'))

        ws = None
        montoDesde = -1
        error = False
        try:
            ws = self.ws_auth()

            _logger.info('Trying to push CUIT to AFIP...')
            cuit_consultada = invoice.partner_id and invoice.partner_id.vat
            if not cuit_consultada:
                _logger.info('Denied, partner without vat.')
                return False
            montoDesde = ws.ConsultarMontoObligadoRecepcion(cuit_consultada)
        except SoapFault as soap_fault:
            error_msg = '%s: %s' % (
                soap_fault.faultcode,
                soap_fault.faultstring,
            )
            _logger.exception('SOAP Error.')
            _logger.exception(error_msg)
            error = True
        except Exception as e:
            if ws and ws.Excepcion:
                error_msg = ws.Excepcion
                _logger.exception('WSFE Error.')
                _logger.exception(error_msg)
            else:
                error_msg = str(e)
                _logger.exception('Internal Error.')
                _logger.exception(error_msg)
                error = True

        if error:
            raise ValueError('Something gone wrong.')

        if not ws or ws.Resultado == 'N':
            _logger.info('Partner NOT obliged.')
            return False
        else:
            _logger.info('Partner obliged.')
            return montoDesde
