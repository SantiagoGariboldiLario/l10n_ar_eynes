# -- coding: utf-8 --
##############################################################################
#
#   Copyright (c) 2022-2023 Eynes SRL (Eynes - Ingenieria del software)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
#
##############################################################################

import logging
from odoo import fields, models

_logger = logging.getLogger(__name__)


class AccountMappingFiscalYearClosing(models.Model):
    _name = 'account.mapping.fiscal.year.closing'
    _description = 'Account Mapping Fiscal Year Closing'

    name = fields.Char('Description', size=60)
    destination_account_id = fields.Many2one('account.account', 'Destination Account', ondelete='cascade')
    fiscal_year_close_id = fields.Many2one(
        'fiscal.year.closing', 'Fiscal Year Closing', ondelete='cascade', required=True
    )
    source_group_id = fields.Many2one('account.group', 'Group', required=True, ondelete='cascade')


class AccountMappingFiscalYearClosingLossProfit(models.Model):
    _name = 'account.mapping.fiscal.year.closing.loss.profit'
    _description = 'Account Mapping Fiscal Year Closing Loss Profit'

    name = fields.Char('Description', size=60)
    destination_account_id = fields.Many2one(
        'account.account', 'Destination Account', required=False, ondelete='cascade'
    )
    fiscal_year_close_id = fields.Many2one(
        'fiscal.year.closing', 'Fiscal Year Closing', ondelete='cascade', required=True
    )
    source_group_id = fields.Many2one('account.group', 'Source Group', required=True, ondelete='cascade')


class AccountMappingFiscalYearClosingNetLossProfit(models.Model):
    _name = 'account.mapping.fiscal.year.closing.net.loss.profit'
    _description = 'Account Mapping Fiscal Year Closing Net Loss Profit'

    name = fields.Char('Description', size=60)
    destination_account_id = fields.Many2one(
        'account.account', 'Destination Account', required=False, ondelete='cascade'
    )
    fiscal_year_close_id = fields.Many2one(
        'fiscal.year.closing', 'Fiscal Year Closing', ondelete='cascade', required=True
    )
    source_group_id = fields.Many2one('account.group', 'Source Group', required=True, ondelete='cascade')
