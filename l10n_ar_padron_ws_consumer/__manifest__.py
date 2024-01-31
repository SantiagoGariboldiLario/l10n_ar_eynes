###############################################################################
#
#    Copyright (c) 2023 Eynes/E-MIPS (www.eynes.com.ar)
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program. If not, see <http://www.gnu.org/licenses/>.
#
###############################################################################
# pylint: disable=manifest-required-author, missing-readme

{
    'name': 'l10n Argentina - Padron WS Consumer',
    'version': '15.0.2.0.0',
    'author': 'Eynes',
    'website': 'https://gitlab.eynes.com.ar/localization/l10n_ar_eynes',
    'license': 'AGPL-3',
    'category': 'Accounting/Accounting',
    'depends': [
        'base',
        'contacts',
        'l10n_ar_eynes',
        'month_year_widget',
    ],
    'data': [
        'data/cron_data.xml',
        'data/perception_data.xml',
        'data/retention_data.xml',
        'data/ir_config_parameter.xml',
        'views/account_journal_view.xml',
        'views/res_partner_view.xml',
    ],
    "external_dependencies": {},
    # "pre_init_hook": "pre_init_hook",
    'installable': True,
    'application': True,
}
