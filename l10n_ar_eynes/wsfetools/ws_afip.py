##############################################################################
#   Copyright (c) 2019 Eynes/E-MIPS (www.eynes.com.ar)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
##############################################################################

import logging
from datetime import datetime

from odoo import _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

AFIP_DATE_FORMAT = '%Y%m%d'
# AFIP Requests a (13, 2) format for amounts:
AFIP_DECIMAL_PRESICION = 2


class WSParser:
    def _afip_round(self, data):
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, float):
                    data[key] = round(value, AFIP_DECIMAL_PRESICION)
                if isinstance(value, dict):
                    self._afip_round(value)
                if isinstance(value, list):
                    for item in value:
                        self._afip_round(item)
        elif isinstance(data, (int, float)):
            return round(data, AFIP_DECIMAL_PRESICION)
        return True

    def _convert_date_to_AFIP_format(self, date):
        return date.strftime(AFIP_DATE_FORMAT)

    def clean_result_date(self, date):
        if date == 'NULL':
            return False
        return datetime.strptime(date, AFIP_DATE_FORMAT)

    def parse_errors(self, ws):
        excep_msg = '' if '0: ok' in ws.Excepcion.lower() else ws.Excepcion
        error_msg = '' if '0: ok' in ws.ErrMsg.lower() else ws.ErrMsg
        obs_msg = '' if '0: ok' in ws.Obs.lower() else ws.Obs
        if excep_msg or error_msg or obs_msg:
            return """
                %s
                %s
                %s
                """ % (
                excep_msg,
                error_msg,
                obs_msg,
            )
        return ''

    def parse_errors_raise(self, ws, title):
        error_msg = ""
        if ws.Errores:
            error_msg += _(
                """
                Error trying to %(title)s.
                """,
                title=title,
            )
            for error in ws.Errores:
                error_msg += error
        if ws.Eventos:
            error_msg += _(
                """
                Events trying to %(title)s.
                """,
                title=title,
            )
            for event in ws.Eventos:
                error_msg += event

        if error_msg:
            _logger.info(error_msg)
            raise UserError(error_msg)
