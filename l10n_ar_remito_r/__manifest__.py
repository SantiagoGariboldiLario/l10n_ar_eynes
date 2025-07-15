###############################################################################
#
#    Copyright (c) 2025 Eynes/E-MIPS (www.eynes.com.ar)
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
# pylint: disable=manifest-required-author, missing-readme, pointless-statement

{
    'name': 'Remito R',
    'version': '17.0.1.0.0',
    'author': 'Eynes',
    'website': 'https://gitlab.eynes.com.ar/localization/l10n_ar_eynes',
    'license': 'AGPL-3',
    'category': 'Accounting/Accounting',
    'depends': ['base', 'contacts', 'stock', 'l10n_ar_eynes'],
    'data': [
        'report/remito_r.xml',
        'views/res_company_views.xml',
        'views/stock_picking_views.xml',
    ],
    "demo": [],
    'assets': {},
    'installable': True,
    "external_dependencies": {"python": []},
}
