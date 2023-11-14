##############################################################################
#   Copyright (c) 2019 Eynes/E-MIPS (www.eynes.com.ar)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
##############################################################################

import logging

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
