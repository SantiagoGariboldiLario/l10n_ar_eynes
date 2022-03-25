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
        'views/account_fiscal_position_views.xml',
        'views/res_document_type_views.xml',
        'views/res_voucher_type_views.xml',
        'views/account_check_views.xml',
        'views/treasury_menuitems.xml',
        'wizard/update_journal_period_view.xml',
        'wizard/create_checkbook_wizard_view.xml',
        'security/ir.model.access.csv',
        'data/fiscal_position_data.xml',
        'data/account_taxes_data.xml',
        'data/res_document_type_data.xml',
        'data/res_voucher_type_data.xml',
    ],
    'installable': True,
    'application': True,
}
