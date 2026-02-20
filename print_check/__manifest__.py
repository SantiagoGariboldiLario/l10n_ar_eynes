###############################################################################
#
#    Copyright (c) 2021 Eynes/E-MIPS (www.eynes.com.ar)
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
{
    'name': 'Print check',
    'author': 'Eynes SRL',
    'license': 'AGPL-3',
    'version': '17.0.0.0.0',
    'website': 'https://gitlab.eynes.com.ar/localization/l10n_ar_eynes',
    'depends': ['l10n_ar_eynes', 'sign_oca'],
    'data': [
        'security/ir.model.access.csv',
        'wizard/print_check_wizard.xml',
        'views/account_check_views.xml',
        'views/menuitem.xml',
        'data/fields_data.xml',
    ],
}
