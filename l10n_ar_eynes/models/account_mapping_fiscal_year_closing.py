##############################################################################
#
#   Copyright (c) 2022-2023 Eynes SRL (Eynes - Ingenieria del software)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
#
##############################################################################

import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)

ACCOUNT_ACCOUNT_TYPE_SELECTION = [
    ("asset_receivable", "Receivable"),
    ("asset_cash", "Bank and Cash"),
    ("asset_current", "Current Assets"),
    ("asset_non_current", "Non-current Assets"),
    ("asset_prepayments", "Prepayments"),
    ("asset_fixed", "Fixed Assets"),
    ("liability_payable", "Payable"),
    ("liability_credit_card", "Credit Card"),
    ("liability_current", "Current Liabilities"),
    ("liability_non_current", "Non-current Liabilities"),
    ("equity", "Equity"),
    ("equity_unaffected", "Current Year Earnings"),
    ("income", "Income"),
    ("income_other", "Other Income"),
    ("expense", "Expenses"),
    ("expense_depreciation", "Depreciation"),
    ("expense_direct_cost", "Cost of Revenue"),
    ("off_balance", "Off-Balance Sheet"),
]


class AccountMappingFiscalYearClosing(models.Model):
    _name = 'account.mapping.fiscal.year.closing'
    _description = 'Account Mapping Fiscal Year Closing'

    name = fields.Char('Description', size=60)
    destination_account_id = fields.Many2one(
        'account.account', 'Destination Account', ondelete='cascade'
    )
    fiscal_year_close_id = fields.Many2one(
        'fiscal.year.closing',
        'Fiscal Year Closing',
        ondelete='cascade',
        required=True,
    )
    source_account_type = fields.Selection(
        selection=ACCOUNT_ACCOUNT_TYPE_SELECTION,
        string='Account type',
        required=True,
    )


class AccountMappingFiscalYearClosingLossProfit(models.Model):
    _name = 'account.mapping.fiscal.year.closing.loss.profit'
    _description = 'Account Mapping Fiscal Year Closing Loss Profit'

    name = fields.Char('Description', size=60)
    destination_account_id = fields.Many2one(
        'account.account',
        'Destination Account',
        required=False,
        ondelete='cascade',
    )
    fiscal_year_close_id = fields.Many2one(
        'fiscal.year.closing',
        'Fiscal Year Closing',
        ondelete='cascade',
        required=True,
    )
    source_account_type = fields.Selection(
        selection=ACCOUNT_ACCOUNT_TYPE_SELECTION,
        string='Account type',
        required=True,
    )


class AccountMappingFiscalYearClosingNetLossProfit(models.Model):
    _name = 'account.mapping.fiscal.year.closing.net.loss.profit'
    _description = 'Account Mapping Fiscal Year Closing Net Loss Profit'

    name = fields.Char('Description', size=60)
    destination_account_id = fields.Many2one(
        'account.account',
        'Destination Account',
        required=False,
        ondelete='cascade',
    )
    fiscal_year_close_id = fields.Many2one(
        'fiscal.year.closing',
        'Fiscal Year Closing',
        ondelete='cascade',
        required=True,
    )
    source_account_type = fields.Selection(
        selection=ACCOUNT_ACCOUNT_TYPE_SELECTION,
        string='Account type',
        required=True,
    )
