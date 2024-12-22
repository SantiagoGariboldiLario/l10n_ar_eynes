##############################################################################
#
#   Copyright (c) 2022-2023 Eynes SRL (Eynes - Ingenieria del software)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
#
##############################################################################

import logging
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import _, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class FiscalYearClosingOperationWizard(models.TransientModel):
    _name = 'fiscal.year.closing.operation.wizard'
    _description = 'Fiscal Year Closing Operation Wizard'

    def _checkings(self, closing):
        if closing.check_draft_moves:
            self._check_draft_moves(closing)

        if closing.check_invalid_period_moves:
            self._check_invalid_period_moves(closing)

        if closing.check_unbalanced_moves:
            self._check_unbalanced_moves(closing)

    def _pre_run(self, closing):
        if closing.create_loss_profit_move and not closing.loss_profit_move_id:
            self.create_closing_move('loss_profit', closing)
        if not closing.create_loss_profit_move and closing.loss_profit_move_id:
            self.remove_move('loss_profit', closing)

        if closing.create_closing_move and not closing.closing_move_id:
            self.create_closing_move('close', closing)
        if not closing.create_closing_move and closing.closing_move_id:
            self.remove_move('close', closing)

        if closing.create_opening_move and not closing.opening_move_id:
            self.create_opening_move('open', closing)
        if not closing.create_opening_move and closing.opening_move_id:
            self.remove_move('open', closing)

        if closing.create_recpam and not closing.recpam_move_id:
            move_id = self.create_recpam_move(closing)
            if move_id:
                closing.write({'recpam_move_id': move_id})
        if not closing.create_recpam and closing.recpam_move_id:
            self.remove_move('recpam', closing)

    def run(self):
        FiscalYearClosing = self.env['fiscal.year.closing']

        active_ids = self.env.context.get('active_ids', False)
        if not active_ids:
            raise ValidationError(_('No active ID found'))

        closing = FiscalYearClosing.browse(active_ids)

        self._checkings(closing)

        self._pre_run(closing)

        if (
            not closing.create_closing_move
            and not closing.create_loss_profit_move
            and not closing.create_opening_move
        ):
            closing.action_cancel()
        else:
            closing.action_run()

        return {'type': 'ir.actions.act_window_close'}

    def _check_invalid_period_moves(self, closing):
        AccountMove = self.env['account.move']

        closing_date_from = closing.closing_date_range_id.date_start
        closing_date_to = closing.closing_date_range_id.date_end
        date_from = closing.closing_id.date_from
        date_to = closing.closing_id.date_to

        invalid_moves = AccountMove.search(
            [
                '|',
                '&',
                '&',
                ('date', '>=', closing_date_from),
                ('date', '<=', closing_date_to),
                '|',
                ('date', '<', date_from),
                ('date', '>', date_to),
                '|',
                ('date', '<', closing_date_from),
                ('date', '>', closing_date_to),
                ('date', '>=', date_from),
                ('date', '<=', date_to),
            ]
        )
        if invalid_moves:
            invalid_msg = '\n'.join(
                [
                    'ID: %s | Date: %s | Number: %s | Ref.: %s'
                    % (move.id, move.date, move.name, move.ref)
                    for move in invalid_moves
                ]
            )
            msg = (
                _(
                    'One or more moves with invalid period or date found on the fiscal year: \n%s'
                )
                % invalid_msg
            )

            raise ValidationError(msg)

    def _check_draft_moves(self, closing):
        AccountMove = self.env['account.move']
        DateRange = self.env['date.range']

        excluded_ids = [
            closing.loss_profit_date_range_id.id,
            closing.closing_date_range_id.id,
        ]

        excluded_date_ranges = DateRange.search([('id', 'in', excluded_ids)])
        excluded_date_start = excluded_date_ranges.mapped('date_start')
        excluded_date_end = excluded_date_ranges.mapped('date_end')

        date_ranges = closing.closing_id.filtered(
            lambda a: a.date_from not in excluded_date_start
            and a.date_to not in excluded_date_end
        )

        draft_moves = False

        msg = ''

        for date_range in date_ranges:
            draft_moves = AccountMove.search(
                [
                    ('date', '<=', date_range.date_to),
                    ('date', '>=', date_range.date_from),
                    ('state', '=', 'draft'),
                ]
            )
            if draft_moves:
                msg += '\n'.join(
                    [
                        'ID: %s | Date: %s | Number: %s | Ref.: %s'
                        % (move.id, move.date, move.name, move.ref)
                        for move in draft_moves
                    ]
                )

        if msg:
            raise ValidationError(
                _('One or more draft moves found: \n%s') % msg
            )

    def _check_unbalanced_moves(self, closing):
        DateRange = self.env['date.range']

        msg = ''

        excluded_ids = [
            closing.loss_profit_date_range_id.id,
            closing.closing_date_range_id.id,
        ]

        excluded_date_ranges = DateRange.search([('id', 'in', excluded_ids)])
        excluded_date_start = excluded_date_ranges.mapped('date_start')
        excluded_date_end = excluded_date_ranges.mapped('date_end')

        date_ranges = closing.closing_id.filtered(
            lambda a: a.date_from != excluded_date_start
            and a.date_to != excluded_date_end
        )
        for date_range in date_ranges:
            query = """SELECT am.id, am.date, am.ref, am.name
                FROM account_move am
                LEFT JOIN account_move_line aml ON aml.move_id = am.id
                WHERE am.date BETWEEN %s AND %s
                GROUP BY am.id, am.date, am.ref, am.name
                HAVING ABS(SUM(COALESCE(debit, 0) - COALESCE(credit, 0))) > 0.001
            """

            vals = (date_range.date_from, date_range.date_to)

            self.env.cr.execute(query, vals)

            res = self.env.cr.dictfetchall()
            if res:
                msg += '\n'.join(
                    [
                        'ID: %(id)s | Date: %(date)s | Number: %(name)s | Ref.: %(ref)s'
                        % move
                        for move in res
                    ]
                )

        if msg:
            raise ValidationError(
                _('One or more unbalanced moves found: \n%s') % msg
            )

    def _get_balance(self, account, fiscal_year):
        query = """SELECT SUM(aml.debit - aml.credit) AS balance
            FROM account_move_line AS aml
            JOIN account_move AS am ON am.id = aml.move_id
            WHERE am.date BETWEEN %(date_from)s AND %(date_to)s
                AND aml.account_id = %(account_id)s
                AND am.company_id = %(company_id)s
            GROUP BY aml.account_id
        """
        vals = {
            'account_id': account.id,
            'company_id': account.company_id.id,
            'date_from': fiscal_year.date_from,
            'date_to': fiscal_year.date_to,
        }

        self.env.cr.execute(query, vals)

        res = self.env.cr.fetchone()
        res = res and res[0] or 0.0

        return res

    def _get_loss_profit_data(self, closing):
        if not closing.loss_profit_date:
            raise ValidationError(_('Loss & profit date must be defined'))

        if not closing.loss_profit_description:
            raise ValidationError(
                _('Loss & profit description must be defined')
            )

        if not closing.loss_profit_journal_id:
            raise ValidationError(_('Loss & profit journal must be defined'))

        if not closing.loss_profit_date_range_id:
            raise ValidationError(_('Loss & profit period must be defined'))

        return {
            'date': closing.loss_profit_date,
            'journal_id': closing.loss_profit_journal_id.id,
            'ref': closing.loss_profit_description,
        }

    def _get_closing_data(self, closing):
        if not (closing.loss_profit_move_id and closing.loss_profit_move_id.id):
            raise ValidationError(
                _(
                    'Loss & profit move must exist before creating a closing move'
                )
            )

        if not closing.closing_date:
            raise ValidationError(_('The closing date must be defined'))

        if not closing.closing_description:
            raise ValidationError(_('The closing description must be defined'))

        if not closing.closing_journal_id:
            raise ValidationError(_('The closing journal must be defined'))

        if not closing.closing_date_range_id:
            raise ValidationError(_('The closing period must be defined'))

        return {
            'date': closing.closing_date,
            'journal_id': closing.closing_journal_id.id,
            'ref': closing.closing_description,
        }

    def _get_accounts_from_group(self, group, closing):
        AccountAccount = self.env['account.account']

        company_id = closing.company_id.id if closing.company_id else False

        accounts = AccountAccount.search(
            [
                ('account_type', '=', group),
                ('company_id', 'in', [company_id, False]),
            ]
        )

        return accounts

    def create_closing_move(self, operation, closing):
        AccountMove = self.env['account.move']
        DecimalPrecision = self.env['decimal.precision']

        data = {}
        destination_account_totals = {}

        mapping_ids = []
        move_lines = []

        fiscal_year = closing.closing_id

        if operation == 'close':
            mapping_ids = closing.closing_account_mapping_ids

            data = self._get_closing_data(closing)
        elif operation == 'loss_profit':
            mapping_ids = closing.loss_profit_account_mapping_ids

            data = self._get_loss_profit_data(closing)
        else:
            assert operation in (
                'close',
                'loss_profit',
            ), 'The operation is not supported'

        for mapping in mapping_ids:
            destination_account = mapping.destination_account_id
            if destination_account:
                destination_account_totals[
                    destination_account.id
                ] = destination_account_totals.get(destination_account.id, 0)

            group = mapping.source_account_type
            accounts = self._get_accounts_from_group(group, closing)
            for account in accounts:
                balance = self._get_balance(account, fiscal_year)

                if (
                    round(
                        abs(balance), DecimalPrecision.precision_get('Account')
                    )
                    > 0
                ):
                    line_vals = {
                        'account_id': account.id,
                        'credit': balance > 0 and balance,
                        'debit': balance < 0 and -balance,
                    }
                    line_vals.update(data)
                    move_lines.append(line_vals)

                    if destination_account:
                        destination_account_totals[
                            destination_account.id
                        ] -= balance

        for key in destination_account_totals.keys():
            balance = destination_account_totals[key]

            line_vals = {
                'account_id': key,
                'credit': balance > 0 and balance,
                'debit': balance < 0 and -balance,
            }
            line_vals.update(data)
            move_lines.append(line_vals)

        ctx = self.env.context.copy()
        ctx['account_period_prefer_special'] = True

        if move_lines:
            move_data = data.copy()
            move_data.update(
                {
                    'line_ids': [(0, 0, line) for line in move_lines],
                    'is_closing': True,
                }
            )

            move = AccountMove.with_context(**ctx).create(move_data)
            if move:
                if operation == 'close':
                    closing.write({'closing_move_id': move.id})
                elif operation == 'loss_profit':
                    closing.write({'loss_profit_move_id': move.id})
                else:
                    assert operation in (
                        'close',
                        'loss_profit',
                    ), 'The operation is not supported'

            return move

        return False

    def create_opening_move(self, operation, closing):
        AccountMove = self.env['account.move']

        if operation != 'open':
            assert operation in ('open'), 'The operation is not supported'

        closing_move = None
        date = None
        description = None
        journal_id = None

        closing_move = closing.closing_move_id

        if not closing_move:
            raise ValidationError(
                _('The closing move must exist to create the opening move')
            )

        if not closing_move.line_ids:
            raise ValidationError(_('The closing move shouldn\'t be empty'))

        if not closing.opening_date:
            raise ValidationError(_('The opening date must be defined'))

        if not closing.opening_description:
            raise ValidationError(_('The opening description must be defined'))

        if not closing.opening_journal_id:
            raise ValidationError(_('The opening journal must be defined'))

        if not closing.opening_date_range_id:
            raise ValidationError(_('The opening period must be defined'))

        date = closing.opening_date
        description = closing.opening_description
        journal_id = closing.opening_journal_id.id

        move_lines = []

        for line in closing_move.line_ids:
            move_lines.append(
                {
                    'account_id': line.account_id.id,
                    'credit': line.debit,
                    'date': date,
                    'debit': line.credit,
                    'journal_id': journal_id,
                    'name': description,
                }
            )

        if move_lines:
            move = AccountMove.create(
                {
                    'date': date,
                    'journal_id': journal_id,
                    'line_ids': [(0, 0, line) for line in move_lines],
                    'ref': description,
                    'is_opening': True,
                }
            )
            if move:
                closing.write({'opening_move_id': move.id})

                return move.id

        return False

    def remove_move(self, operation, closing):
        move = None

        if operation == 'close':
            move = closing.closing_move_id

            closing.write({'closing_move_id': None})
        elif operation == 'loss_profit':
            move = closing.loss_profit_move_id

            closing.write({'loss_profit_move_id': None})
        elif operation == 'open':
            move = closing.opening_move_id

            closing.write({'opening_move_id': None})
        elif operation == 'recpam':
            move = closing.recpam_move_id

            closing.write({'recpam_move_id': None})
        else:
            assert operation in (
                'close',
                'loss_profit',
                'open',
            ), 'The operation is not supported'

        assert move and move.id, 'The move to delete must be defined'

        move.unlink()

        return move.id

    def get_coefficient(self, date_from, date_to, fiscal_year, special=False):
        InflationIndex = self.env['inflation.index']

        inflation_indexes = InflationIndex.search(
            [('date', '>=', date_from), ('date', '<=', fiscal_year.date_to)],
            order='date ASC',
        )
        if not inflation_indexes:
            msg = _(
                'There is no inflation index configured fot this fiscal year'
            )

            raise ValidationError(msg)

        date_lst = inflation_indexes.mapped('date')
        base_reg = inflation_indexes.filtered(lambda x: x.date == date_lst[-1])[
            0
        ]  # Last index of Fiscal Year
        target_reg = inflation_indexes.filtered(
            lambda r: r.date <= date_to and r.date >= date_from
        )
        if not target_reg:
            msg = _(
                'There is not index for inflation between %(date_from)s and %(date_to)s.',
                date_from=date_from,
                date_to=date_to,
            )
            raise ValidationError(msg)
        if len(target_reg) > 1:
            msg = _(
                'There are many indexes for inflation between %(date_from)s and %(date_to)s.',
                date_from=date_from,
                date_to=date_to,
            )
            raise ValidationError(msg)
        base_coeff = base_reg.coefficient
        current_coeff = target_reg[0].coefficient
        if current_coeff == 0:
            return 0
        coefficient = base_coeff / current_coeff
        return coefficient

    def get_accounts_by_period(
        self, date_from, date_to, fiscal_year, coefficient=0
    ):
        query = """
            SELECT mvl.account_id, SUM(mvl.debit - mvl.credit) * (%(coefficient)s-1) AS amount
            FROM account_move_line AS mvl
            LEFT JOIN account_account AS ac ON mvl.account_id = ac.id
            JOIN account_move m ON m.id=mvl.move_id
            WHERE ac.recpam_type = 'reexpressed'
            AND mvl.date >= %(date_from)s
            AND mvl.date <= %(date_to)s
            GROUP BY mvl.account_id;
        """
        if not coefficient:
            coefficient = self.get_coefficient(date_from, date_to, fiscal_year)
        vals = {
            'coefficient': coefficient,
            'date_from': date_from,
            'date_to': date_to,
        }
        self.env.cr.execute(query, vals)
        res = self.env.cr.dictfetchall()
        return res

    def _prepare_move_line(self, desc, journal_id, account_id, amount):
        date = datetime.today().strftime('%Y-%m-%d')
        move_line_vals = {
            'account_id': account_id,
            'debit': amount > 0 and amount,
            'credit': amount < 0 and -amount,
            'name': desc,
            'date': date,
            'journal_id': journal_id,
        }
        return move_line_vals

    def _generate_monthly_periods(self, fiscal_year):
        months = []

        date_from = fiscal_year.date_from
        while fiscal_year.date_to > date_from:
            next_date_from = date_from + relativedelta(months=1)
            date_to = next_date_from - relativedelta(days=1)
            months.append(
                {
                    'date_from': date_from,
                    'date_to': date_to,
                }
            )
            date_from = next_date_from

        return months

    def create_recpam_move(self, closing):
        AccountMove = self.env['account.move']
        DecimalPrecision = self.env['decimal.precision']

        closing_fiscalyear = closing.closing_id
        periods = self._generate_monthly_periods(closing_fiscalyear)
        account_group = {}

        for period in periods:
            vals = self.get_accounts_by_period(
                period['date_from'], period['date_to'], closing_fiscalyear
            )
            for line_vals in vals:
                account_id = line_vals.get('account_id')
                amount = line_vals.get('amount')
                if account_id not in account_group:
                    account_group[account_id] = 0.0
                account_group[account_id] += amount

        move_lines = []
        journal_id = closing.recpam_journal_id.id
        recpam_account_id = closing.recpam_account_id.id
        description = closing.recpam_description
        total_amount = 0.0
        for account_id, amount in account_group.items():
            precision = DecimalPrecision.precision_get('account')
            line_amount = round(amount, precision)
            line_vals = self._prepare_move_line(
                description, journal_id, account_id, line_amount
            )
            total_amount += line_amount
            move_lines.append(line_vals)

        total_amount = -1 * total_amount
        counterpart_line = self._prepare_move_line(
            description, journal_id, recpam_account_id, total_amount
        )
        move_lines.append(counterpart_line)
        move = AccountMove.create(
            {
                'ref': closing.recpam_description,
                'journal_id': closing.recpam_journal_id.id,
                'line_ids': [(0, 0, line) for line in move_lines],
            }
        )
        ctx = dict(self.env.context)
        ctx['account_period_prefer_special'] = True
        move.with_context(**ctx).write(
            {
                'date': closing_fiscalyear.date_to,
            }
        )
        return move.id
