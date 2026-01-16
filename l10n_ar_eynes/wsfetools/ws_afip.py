##############################################################################
#   Copyright (c) 2019 Eynes/E-MIPS (www.eynes.com.ar)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
##############################################################################

import json
import logging
import urllib.request
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

AFIP_DATE_FORMAT = '%Y%m%d'
# AFIP Requests a (13, 2) format for amounts:
AFIP_DECIMAL_PRESICION = 2
NOW = datetime.now()
URL = f'https://nolaborables.com.ar/api/v2/feriados/{NOW.year}'  # noqa: E231


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

    def _get_last_working_day(self, date):
        """
        Devuelve el día hábil anterior a determinada fecha
        """
        holidays = []
        try:
            res = urllib.request.urlopen(URL)
            json_data = json.loads(res.read())
            for data in json_data:
                str_day = str(NOW.year) + str(data['mes']) + str(data['dia'])
                holiday = datetime.strptime(str_day, "%Y%m%d").date()
                holidays.append(holiday)
        except Exception as e:
            raise UserError(_('Unable to get holidays from %s') % URL) from e

        is_holiday = True
        is_weekend = True
        while is_holiday or is_weekend:
            date = date - relativedelta(days=1)
            is_weekend = date.weekday() >= 5
            is_holiday = date in holidays

        return date

    def clean_result_date(self, date):
        if not date or date == 'NULL' or date == 'None':
            return False
        return datetime.strptime(date, AFIP_DATE_FORMAT)

    def parse_associated_voucher(self, invoice):
        CbtesAsoc = []
        for associated_inv in invoice.associated_inv_ids:
            tipo_cbte = associated_inv.get_voucher_type()
            pos, number = associated_inv.name.split('-')
            cbte_fch = self._convert_date_to_AFIP_format(
                associated_inv.invoice_date
            )
            CbteAsoc = {
                'Tipo': tipo_cbte,
                'PtoVta': int(pos),
                'Nro': int(number),
                'Cuit': invoice.company_id.partner_id.vat,
                'CbteFch': cbte_fch,
            }
            CbtesAsoc.append(CbteAsoc)
        return CbtesAsoc

    def parse_errors(self, ws):
        excep_msg = '' if '0: ok' in ws.Excepcion.lower() else ws.Excepcion
        error_msg = '' if '0: ok' in ws.ErrMsg.lower() else ws.ErrMsg
        if excep_msg or error_msg:
            return """
                %s
                %s
                """ % (
                excep_msg,
                error_msg,
            )
        return ''

    def parse_errors_raise(self, ws, title):
        error_msg_parsed = self.parse_errors(ws)

        if error_msg_parsed:
            error_msg = _(
                """
                Error trying to %(title)s.
                %(error_msg)s
                """,
                title=title,
                error_msg=error_msg_parsed,
            )
            _logger.info(error_msg)
            raise UserError(error_msg)
