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
    'name': 'Pos AR WSFE',
    'version': '19.0.1.3.0',
    'author': 'Eynes',
    'website': 'https://gitlab.eynes.com.ar/localization/l10n_ar_eynes/',
    'license': 'AGPL-3',
    'category': 'Accounting/Accounting',
    'depends': [
        'l10n_ar_eynes',
        'point_of_sale',
    ],
    'data': [
        'views/account_report.xml',
        'views/pos_config_views.xml',
        'views/pos_order_views.xml',
        'views/res_company_views.xml',
        'security/ir.model.access.csv',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'l10n_ar_pos_wsfe/static/src/js/account_fiscal_position.js',
            'l10n_ar_pos_wsfe/static/src/js/account_move_service.js',
            'l10n_ar_pos_wsfe/static/src/js/control_buttons.js',
            'l10n_ar_pos_wsfe/static/src/js/models.js',
            'l10n_ar_pos_wsfe/static/src/js/payment.js',
            'l10n_ar_pos_wsfe/static/src/js/order_receipt.js',
            'l10n_ar_pos_wsfe/static/src/js/order_payment_validation.js',
            'l10n_ar_pos_wsfe/static/src/js/pos_store_receipt.js',
            'l10n_ar_pos_wsfe/static/src/js/product.js',
            'l10n_ar_pos_wsfe/static/src/xml/OrderSummary.xml',
            'l10n_ar_pos_wsfe/static/src/xml/PaymentScreen.xml',
            'l10n_ar_pos_wsfe/static/src/xml/OrderReceipt.xml',
            'l10n_ar_pos_wsfe/static/src/xml/ControlButtons.xml',
        ],
    },
    "external_dependencies": {},
    'installable': True,
    'application': True,
}
