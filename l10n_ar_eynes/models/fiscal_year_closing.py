##############################################################################
#
#   Copyright (c) 2022-2023 Eynes SRL (Eynes - Ingenieria del software)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
#
##############################################################################

import logging
from datetime import datetime

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class FiscalYearClosing(models.Model):
    _name = 'fiscal.year.closing'
    _description = 'Fiscal Year Closing'

    check_draft_moves = fields.Boolean('Check Draft Moves')
    check_invalid_period_moves = fields.Boolean(
        'Check Invalid Period or Date Moves'
    )
    check_unbalanced_moves = fields.Boolean('Check Unbalanced Moves')
    closing_id = fields.Many2one(
        'account.fiscal.year',
        'Closing Fiscal Year',
        required=True,
        ondelete='cascade',
        default=lambda self: self._get_default_closing_id(),
    )
    closing_account_mapping_ids = fields.One2many(
        'account.mapping.fiscal.year.closing',
        'fiscal_year_close_id',
        'Closing Fiscal Year Account Mappings',
    )
    closing_date = fields.Date('Closing Fiscal Year Date')
    closing_description = fields.Char(
        'Closing Fiscal Year Description', size=60
    )
    closing_journal_id = fields.Many2one(
        'account.journal', 'Closing Fiscal Year Journal'
    )
    closing_move_id = fields.Many2one(
        'account.move',
        'Closing Fiscal Year Move',
        ondelete='set null',
        readonly=True,
    )
    closing_date_range_id = fields.Many2one('date.range', 'Period')
    company_id = fields.Many2one(
        'res.company',
        'Company',
        ondelete='cascade',
        readonly=True,
        required=True,
        default=lambda self: self._get_default_company_id(),
    )
    create_closing_move = fields.Boolean('Create Closing Fiscal Year')
    create_loss_profit_move = fields.Boolean('Create Loss & Profit Move')
    create_opening_move = fields.Boolean('Create Opening Fiscal Year Move')
    create_recpam = fields.Boolean('Create RECPAM')
    loss_profit_account_mapping_ids = fields.One2many(
        'account.mapping.fiscal.year.closing.loss.profit',
        'fiscal_year_close_id',
        'Loss & Profit Account Mappings',
    )
    loss_profit_date = fields.Date('Loss & Profit Date')
    loss_profit_description = fields.Char('Loss & Profit Description', size=60)
    loss_profit_journal_id = fields.Many2one(
        'account.journal', 'Loss & Profit Journal'
    )
    loss_profit_move_id = fields.Many2one(
        'account.move', 'Loss & Profit Move', ondelete='set null', readonly=True
    )
    loss_profit_date_range_id = fields.Many2one(
        'date.range',
        'Net Loss & Profit Period',
    )
    name = fields.Char('Description', size=60, required=True)
    opening_id = fields.Many2one(
        'account.fiscal.year',
        'Opening Fiscal Year',
        required=True,
        ondelete='cascade',
        default=lambda self: self._get_default_opening_id(),
    )
    opening_date = fields.Date('Opening Fiscal Year Date')
    opening_description = fields.Char(
        'Opening Fiscal Year Description', size=60
    )
    opening_journal_id = fields.Many2one(
        'account.journal', 'Opening Fiscal Year Journal'
    )
    opening_move_id = fields.Many2one(
        'account.move',
        'Opening Fiscal Year Move',
        ondelete='set null',
        readonly=True,
    )
    opening_date_range_id = fields.Many2one(
        'date.range',
        'Opening Fiscal Year Period',
    )
    recpam_account_id = fields.Many2one(
        'account.account', 'RECPAM Account', ondelete='set null'
    )
    recpam_description = fields.Char('RECPAM Description', size=60)
    recpam_journal_id = fields.Many2one('account.journal', 'RECPAM Journal')
    recpam_move_id = fields.Many2one(
        'account.move', 'RECPAM Move', ondelete='set null', readonly=True
    )
    state = fields.Selection(
        [
            ('new', 'New'),
            ('draft', 'Draft'),
            ('in_progress', 'In Progress'),
            ('done', 'Done'),
            ('canceled', 'Canceled'),
        ],
        'Status',
        default=lambda *a: 'new',
    )

    _sql_constraints = [
        (
            'closing_id_uniq',
            'unique(closing_id)',
            'The closing fiscal year must be unique!',
        ),
        ('name_uniq', 'unique(name)', 'The name must be unique!'),
        (
            'opening_id_uniq',
            'unique(opening_id)',
            'The opening fiscal year must be unique!',
        ),
    ]

    def _get_default_closing_id(self):
        AccountFiscalYear = self.env['account.fiscal.year']

        company = (
            self.env.user.company_id.id if self.env.user.company_id else False
        )
        str_date = '%s-06-01' % (datetime.now().year - 1)

        fiscal_year = AccountFiscalYear.search(
            [
                ('company_id', 'in', [company, False]),
                ('date_from', '<=', str_date),
                ('date_to', '>=', str_date),
            ],
            limit=1,
        )

        return fiscal_year

    def _get_default_company_id(self):
        return self.env.user.company_id

    def _get_default_opening_id(self):
        AccountFiscalYear = self.env['account.fiscal.year']

        company = (
            self.env.user.company_id.id if self.env.user.company_id else False
        )
        str_date = '%s-06-01' % datetime.now().year

        fiscal_year = AccountFiscalYear.search(
            [
                ('company_id', 'in', [company, False]),
                ('date_from', '<=', str_date),
                ('date_to', '>=', str_date),
            ],
            limit=1,
        )

        return fiscal_year

    def _get_closing_period(self, fiscal_year):
        DateRange = self.env['date.range']

        period = DateRange.search(
            [('date_start', '=', fiscal_year.closing_id.date_to)], limit=1
        )
        if period:
            return period.id

        return False

    def _get_journal_id(self, fiscal_year):
        AccountJournal = self.env['account.journal']

        assert fiscal_year.company_id, 'You should select a company'

        company = fiscal_year.company_id.id if fiscal_year.company_id else False

        journal = AccountJournal.search(
            [
                ('company_id', 'in', [company, False]),
                '|',
                ('code', '=', 'GRAL'),
                ('name', 'ilike', 'General'),
            ],
            limit=1,
        )
        if journal:
            return journal.id

        return False

    def _get_loss_profit_period(self, fiscal_year):
        DateRange = self.env['date.range']

        period = DateRange.search(
            [('date_start', '=', fiscal_year.closing_id.date_to)], limit=1
        )
        if period:
            return period.id

        return False

    def _get_opening_period(self, fiscal_year):
        DateRange = self.env['date.range']

        period = DateRange.search(
            [('date_end', '=', fiscal_year.closing_id.date_from)], limit=1
        )
        if period:
            return period.id

        return False

    def action_draft(self):
        if self.closing_account_mapping_ids:
            self.write({'state': 'draft'})
        else:
            data = {
                'check_draft_moves': True,
                'check_invalid_period_moves': True,
                'check_unbalanced_moves': True,
                'closing_date': self.closing_id.date_to,
                'closing_description': _('Fiscal Year Closing'),
                'closing_journal_id': self._get_journal_id(self),
                'closing_date_range_id': self._get_closing_period(self),
                'create_closing_move': True,
                'create_loss_profit_move': True,
                'create_opening_move': True,
                'create_recpam': True,
                'loss_profit_date': self.closing_id.date_to,
                'loss_profit_description': _('Loss & Profit'),
                'loss_profit_journal_id': self._get_journal_id(self),
                'loss_profit_date_range_id': self._get_loss_profit_period(self),
                'opening_date': self.opening_id.date_from,
                'opening_description': _('Fiscal Year Opening'),
                'opening_journal_id': self._get_journal_id(self),
                'opening_date_range_id': self._get_opening_period(self),
                'state': 'draft',
            }
            self.write(data)

        return True

    def action_run(self):
        self.write({'state': 'in_progress'})
        return True

    def action_confirm(self):
        for rec in self:
            if not rec.loss_profit_move_id:
                raise UserError(_('Loss & Profit move is required'))

            if not rec.closing_move_id:
                raise UserError(_('Closing move is required'))

            if not rec.opening_move_id:
                raise UserError(_('Opening move is required'))

            if not rec.recpam_move_id:
                raise UserError(_('RECPAM move is required'))

        self.write({'state': 'done'})

        return True

    def action_cancel(self):
        FiscalYearClosing = self.env['fiscal.year.closing']

        ctx = self.env.context.copy()
        user = self.env.user
        ctx['lang'] = ctx.get('lang') or user.lang

        FiscalYearClosing.with_context(**ctx).write(
            {
                'check_draft_moves': False,
                'check_invalid_period_moves': False,
                'check_unbalanced_moves': False,
                'create_closing_move': False,
                'create_loss_profit_move': False,
                'create_opening_move': False,
                'create_recpam': False,
            }
        )

        for rec in self:
            if rec.loss_profit_move_id:
                rec.loss_profit_move_id.unlink()

            if rec.closing_move_id:
                rec.closing_move_id.unlink()

            if rec.opening_move_id:
                rec.opening_move_id.unlink()

            if rec.recpam_move_id:
                rec.recpam_move_id.unlink()

        self.write({'state': 'canceled'})

        return True

    def action_recover(self):
        self.write({'state': 'new'})
        return True
