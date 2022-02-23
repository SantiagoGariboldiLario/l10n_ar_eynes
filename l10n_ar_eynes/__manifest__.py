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
    'name': 'l10n Argentina',
    'version': '15.0.1',
    'author': 'Eynes/E-MIPS',
    'license': 'AGPL-3',
    'description': 'Localization customizations module.',
    'category': 'Accounting/Accounting',
    'depends': ['account', 'sale', 'stock'],
    'data': [
        'views/account_journal_views.xml',
        'views/account_move_views.xml',
        'views/user_journal_rel_views.xml',
        'wizard/update_journal_period_view.xml',
        'security/ir.model.access.csv',
    ],
    'installable': True,
    'application': True,
}
