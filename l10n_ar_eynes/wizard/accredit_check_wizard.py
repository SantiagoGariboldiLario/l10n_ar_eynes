import time

from odoo import _, fields, models
from odoo.exceptions import UserError, ValidationError


class AccreditCheckwizard(models.TransientModel):
    _name = 'accredit.check.wizard'
    _description = 'accredit check wizard'

    date = fields.Date(
        string='Accredit Date',
        required=True,
        default=lambda *a: time.strftime('%Y-%m-%d'),
    )

    def view_init(self, fields_list):
        """
        This method gets overrided to ensure that the check's
        internal type is third_party and its state is 'deposited'
        """
        check = self.env['account.check'].browse(
            self.env.context.get('active_id', False)
        )
        if check:
            if check.internal_type == 'third_party':
                if check.third_party_check_state != 'deposited':
                    raise UserError(
                        _(
                            "Error! The selected checks must be in wallet.\n"
                            "Check %s is not in wallet"
                        )
                        % (check.number)
                    )

        else:
            raise ValidationError(_("Error when searching for the check"))

    def _check_validations(self, checks):
        third_party = checks.filtered(
            lambda check: check.internal_type == 'third_party'
        )

        if checks - third_party:
            raise UserError(_("You can't do this operation for issued checks."))

        # Filter checks that are third-party and not in wallet
        third_party_not_deposited = third_party.filtered(
            lambda check: check.third_party_check_state != 'deposited'
        )
        if third_party_not_deposited:
            raise UserError(
                _(
                    "Error! The selected checks must be deposited. Checks with issues: %s"
                )
                % ', '.join(check.number for check in third_party_not_deposited)
            )

    def action_accredit(self):
        AccountMoveLine = self.env['account.move.line']

        accredit_date = self.date or time.strftime('%Y-%m-%d')

        checks = self.env['account.check'].browse(
            self.env.context.get('active_ids', [])
        )

        if checks:
            self._check_validations(checks)

            for check in checks:
                move_ref = _(
                    'Accredit Check %(check_number)s [%(voucher_number)s]',
                    check_number=check.number,
                    voucher_number=check.deposit_slip,
                )

                move_id = self.env['account.move'].create(
                    {
                        'name': '/',
                        'journal_id': check.deposit_move_id.journal_id.id,
                        'state': 'draft',
                        'date': accredit_date,
                        'ref': move_ref,
                    }
                )

                AccountMoveLine.with_context(check_move_validity=False).create(
                    {
                        'name': _('Check accredit'),
                        # 'centralisation': 'normal',
                        'account_id': check.deposit_bank_id.journal_id.default_account_id.id,
                        'move_id': move_id.id,
                        'journal_id': check.deposit_move_id.journal_id.id,
                        'date': accredit_date,
                        'debit': check.amount,
                        'credit': 0.0,
                        'ref': _(
                            'Accredit Check %(check_number)s on %(acc_number)s',
                            check_number=check.number,
                            acc_number=check.deposit_bank_id.acc_number,
                        ),
                    }
                )
                AccountMoveLine.with_context(check_move_validity=False).create(
                    {
                        'name': _('Check accredit'),
                        # 'centralisation': 'normal',
                        'account_id': check.deposit_bank_id.journal_id.suspense_account_id.id,
                        'move_id': move_id.id,
                        'journal_id': check.deposit_move_id.journal_id.id,
                        'date': accredit_date,
                        'debit': 0.0,
                        'credit': check.amount,
                        'ref': _('Accredit Check %s') % check.number,
                    }
                )
                if check.internal_type == 'third_party':
                    check.write(
                        {
                            'third_party_check_state': 'accredited',
                            'accredit_date': accredit_date,
                            'accredit_move_id': move_id.id,
                        }
                    )

                # Se postea el asiento llamando a la funcion post de account_move.
                # TODO: Se podria poner un check en el wizard
                # para que elijan si postear el asiento o no.
                move_id._post()

        return {'type': 'ir.actions.act_window_close'}
