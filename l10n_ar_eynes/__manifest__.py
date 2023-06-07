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
# pylint: disable=manifest-required-author, missing-readme, pointless-statement

{
    'name': 'l10n Argentina',
    'version': '15.0.0.2.0',
    'author': 'Eynes',
    'website': 'https://gitlab.eynes.com.ar/localization/l10n_ar_eynes',
    'license': 'AGPL-3',
    'category': 'Accounting/Accounting',
    'depends': [
        'sale',
        'stock',
        'purchase',
        'contacts',
        'hr',
        'account_check_printing',
        'account_debit_note',
        'account',
        'report_xlsx',
    ],
    'data': [
        'data/fiscal_position_data.xml',
        'data/account_taxes_data.xml',
        'data/res_document_type_data.xml',
        'data/res_voucher_type_data.xml',
        'data/account_default_journals_data.xml',
        'data/account_payment_method_data.xml',
        'data/iibb_situation_data.xml',
        'data/dst_cuit_codes_data.xml',
        'data/ir_sequence_data.xml',
        "data/wsfe_data.xml",
        "data/ir_cron.xml",
        "data/perception_data.xml",
        "data/res_groups_data.xml",
        'security/ir.model.access.csv',
        'security/account_security.xml',
        'security/perception_ir_rule.xml',
        'wizard/deposit_check_wizard_view.xml',
        'wizard/reject_check_wizard_view.xml',
        'wizard/account_change_currency_wizard_view.xml',
        # 'wizard/accredit_check_wizard_view.xml',
        'report/move_line_list_xls.xml',
        'wizard/account_tax_subjournal_view.xml',
        'views/res_config_settigs_views.xml',
        'views/res_partner_views.xml',
        # 'views/res_currency_rate_view.xml',
        'views/res_currency_view.xml',
        'views/account_journal_views.xml',
        'views/account_payment_order_views.xml',
        'views/account_payment_order_other_payments_views.xml',
        'views/account_move_views.xml',
        'views/account_fiscal_position_views.xml',
        'views/account_tax_views.xml',
        'views/res_document_type_views.xml',
        'views/res_voucher_type_views.xml',
        'views/account_check_views.xml',
        'views/reason_rejected_check_views.xml',
        'views/retention_views.xml',
        "views/perception_view.xml",
        'views/res_users_views.xml',
        'views/account_checkbook_views.xml',
        'wizard/create_checkbook_wizard_view.xml',
        'views/treasury_menuitems.xml',
        'views/taxes_menuitems.xml',
        'wizard/update_journal_period_view.xml',
        "wizard/wsaa_config_renewal.xml",
        'views/wsaa_view.xml',
        'views/certificate_request_view.xml',
        "wizard/wsfe_sinchronize_voucher_view.xml",
        "wizard/wsfe_massive_sinchronize_view.xml",
        "views/wsfe_view.xml",
        "views/res_company_view.xml",
    ],
    'installable': True,
    'application': True,
    "external_dependencies": {
        "python": ["M2Crypto", "OpenSSL", "easywsy", "suds"]
    },
}
