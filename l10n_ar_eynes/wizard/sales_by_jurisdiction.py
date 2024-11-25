##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (c) 2019 E-MIPS (http://www.e-mips.com.ar)
#    Copyright (c) 2019 Eynes (http://www.eynes.com.ar)
#    All Rights Reserved. See AUTHORS for details.
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General
#    Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class ExportSalesByJurisdictionXLS(models.TransientModel):
    _name = 'export.sales.by.jurisdiction.xls'
    _description = 'Export Sales By Jurisdiction'

    date_from = fields.Date(string='Period From', required=True)
    date_to = fields.Date(string='Period To', required=True)
    company_ids = fields.Many2many('res.company', string='Company')

    def create_report(self):
        report_file_name = 'subjournal_by_jurisdiction'
        company_ids = self.company_ids
        if not company_ids:
            company_ids = self.env['res.company'].search([])
        for company in company_ids:
            report_file_name += '_' + company.name
        data = {
            'print_by': self.env.user.name,
            'date_start': self.date_from,
            'date_stop': self.date_to,
            'company_name': self.env.company.name,
            'dynamic_report': True,
            'company_ids': company_ids.ids,
        }
        return {
            'context': dict(self.env.context, report_file=report_file_name),
            'data': data,
            'type': 'ir.actions.report',
            'report_name': 'l10n_ar_eynes.sales_by_jurisdiction_export_xlsx',
            'report_type': 'xlsx',
            'report_file': '',
            'name': 'Export Subjournal',
        }
