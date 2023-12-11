##############################################################################
#   Copyright (c) 2023 Eynes/E-MIPS (www.eynes.com.ar)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
##############################################################################

import logging
from datetime import datetime

from pyafipws.ws_sr_padron import WSSrPadronA5
from pysimplesoap.client import SoapFault

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


def clean_result_date(date):
    if date == 'NULL':
        return False
    return datetime.strptime(date, '%Y%m%d')


class WsPadronConfig(models.Model):
    _name = "ws.padron.config"
    _inherit = "ws.config"
    _description = "Configuration for Padron"

    _webservice_class = WSSrPadronA5

    @api.depends('config_id', 'config_id.homologation')
    def _compute_url(self):
        url_prod = self.env.ref('l10n_ar_eynes.url_prod_padron').value
        url_homo = self.env.ref('l10n_ar_eynes.url_homo_padron').value
        for rec in self:
            rec.url = url_homo if rec.config_id.homologation else url_prod

    def _get_webservice(self):
        return self.env.ref('l10n_ar_eynes.afipws_service_ws_padron')

    def fetch_data_from_afip(self, invoices):
        self.ensure_one()
        if not self.cuit:
            raise UserError(_("Please configure the company VAT!"))

        ws = self.ws_auth()

        WsRequest = self.env['ws.request']
        WsRequestDetail = self.env['ws.request.detail']
        request = WsRequest.create({'date_request': fields.Datetime.today()})
        qty_processed = 0
        for invoice in invoices:
            # validator.validate_invoice(invoice)
            self._set_invoice_in_ws(ws, invoice)

            _logger.info("Trying to push Inovice data to AFIP...")
            error_msg = ""
            try:
                qty_processed += 1
                ws.CAESolicitar()
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

            if ws.Resultado == "R":
                _logger.warning("AFIP Validation Error. Invoice not approved.")
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
                        'errors': ws.ErrMsg or "",
                        'observations': ws.Obs or "",
                        'events': ws.ErrMsg or "",
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
