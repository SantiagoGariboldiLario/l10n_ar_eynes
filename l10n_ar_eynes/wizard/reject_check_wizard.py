from odoo import _, fields, models
from odoo.exceptions import ValidationError


class RejectIssuedCheckWizard(models.TransientModel):
    _name = 'reject.issued.check.wizard'
    _description = 'Reject issued check wizard'

    reject_date = fields.Date(string='Reject date')
    note = fields.Text(string='Note')
    reason_id = fields.Many2one(
        comodel_name='reason.rejected.check',
        domain="[('type', '=', 'rejected')]",
        string='Reason',
    )
    generate_rejection_journal_entry = fields.Boolean(
        string='Generate Rejection Journal Entry', default=True
    )  # Este campo queda deprecado a partir del 9/5/24, aparentemente SIEMPRE se genera el asiento

    def action_reject(self):
        """action that rejects the issued check"""
        check = self.env['account.check'].browse(
            self.env.context.get('active_id', False)
        )
        if check:
            check.write({'reject_date': self.reject_date, 'note': self.note})
            if self.generate_rejection_journal_entry:
                self.create_rejected_journal_entry(check)
            check.write({'issued_check_state': 'rejected'})
        return {'type': 'ir.actions.act_window_close'}

    def create_rejected_journal_entry(self, check):
        """
        This method generates an invoice which register the
        check rejection as an invoice movement. It also adds the lines to the payment order

        Args:
            check (account.issued.check): check record
        """
        AccoutMoveLine = self.env['account.move.line']

        payment = check.payment_order_id
        journal = self.env.user.company_id.rejected_issued_checks_journal_id
        if not journal:
            raise ValidationError(
                _("No journal configured for rejected checks")
            )

        def_check_account = (
            self.env['account.check.config']
            .search([('company_id', '=', self.env.user.company_id.id)])
            .deferred_account_id.id
        )
        if not def_check_account:
            raise ValidationError(_("No Deferred account id configured"))

        ctx = {
            'date': self.reject_date,
            'check_move_validity': False,
        }

        for payment_line in payment.move_line_ids:
            if payment_line.issued_check_id == check:
                original_move_data = payment.account_move_get()
                original_move_data['journal_id'] = journal.id
                original_move_data['state'] = 'draft'
                move = (
                    self.env['account.move']
                    .with_context(**ctx)
                    .create(original_move_data)
                )

                # Get the name of the account_move just created
                counterpart_account = (
                    self.env['account.account']
                    .search([('code', '=', payment_line.counterpart)])
                    .id
                )
                if not counterpart_account:
                    raise ValidationError(_("No counterpart account found"))
                inverse_supplier_line = {
                    'name': '/',
                    'account_id': counterpart_account,
                    'move_id': move.id,
                    'partner_id': payment_line.partner_id.id,
                    'date': self.reject_date,
                    'credit': payment_line.credit,
                    'debit': 0,
                    'amount_currency': payment_line.amount_currency,
                    'journal_id': original_move_data['journal_id'],
                    'currency_id': payment_line.currency_id.id,
                    'analytic_account_id': payment_line.analytic_account_id.id,
                    'ref': _('Rejected check')
                    + ': '
                    + (payment_line.name or '/'),
                }
                AccoutMoveLine.with_context(**ctx).create(inverse_supplier_line)

                inverse_check_line = {
                    'name': _('Rejected check')
                    + ': '
                    + (payment_line.name or '/'),
                    'account_id': def_check_account,
                    'move_id': move.id,
                    'partner_id': payment_line.partner_id.id,
                    'date': self.reject_date,
                    'credit': 0,
                    'debit': payment_line.credit,
                    'amount_currency': payment_line.amount_currency,
                    'journal_id': original_move_data['journal_id'],
                    'currency_id': payment_line.currency_id.id,
                    'analytic_account_id': payment_line.analytic_account_id.id,
                    'ref': _('Rejected check')
                    + ': '
                    + (payment_line.name or '/'),
                }
                AccoutMoveLine.with_context(**ctx).create(inverse_check_line)
                move.post()


class RejectThirdPartyCheckWizard(models.TransientModel):
    _name = 'reject.third.party.check.wizard'
    _description = 'Reject third party check wizard'

    def _get_journal(self):
        user = self.env.user
        company_id = self.env.context.get('company_id', user.company_id.id)
        journal = self.env['account.journal'].search(
            [('company_id', '=', company_id), ('type', '=', 'sale')], limit=1
        )
        return journal and journal.id or False

    reject_date = fields.Date('Reject date')
    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Journal',
        required=True,
        default=_get_journal,
    )
    expense_line_ids = fields.One2many(
        comodel_name='check.reject.expense',
        inverse_name='reject_id',
        string='Expenses',
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )

    def action_reject(self):
        """
        This method is called when the rejection is confirmed in the wizard.
        It change the state of the 3rd party check to 'rejected' and also creates a move.
        """
        check = self.env['account.check'].browse(self._context.get('active_id'))

        if check:
            check.reject_date = self.reject_date
            partner = check.source_partner_id

            config = self.env['account.check.config'].search(
                [('company_id', '=', check.company_id.id)]
            )
            if not config:
                raise ValidationError(
                    _(
                        'ERROR! There is no check configuration for this Company!'
                    )
                )

            inv_account_id = config.receivable_rejected_account_id
            if not inv_account_id:
                inv_account_id = partner.property_account_receivable_id

            name = _(
                'Debit Note due to rejected check %(check_number)s [%(po_number)s]',
                check_number=check.number or '',
                po_number=check.source_payment_order_id.number,
            )

            invoice_vals = {
                'invoice_origin': _('Check : %s') % check.number,
                'name': name,
                'move_type': 'out_invoice',
                'partner_id': partner.id,
                'journal_id': self.journal_id.id,
                'fiscal_position_id': partner.property_account_position_id.id,
                'company_id': self.company_id.id,
            }
            lines = []
            # Linea del cheque rechazado
            account_id = self.get_account(config, check)
            date_format = (
                self.env["res.lang"]
                .search([("code", "=", self.env.user.lang)])
                .date_format
            )
            rejected_date = self.reject_date.strftime(date_format)
            name = _(
                'Check Rejected %(check_number)s %(rejected_date)s',
                check_number=check.number,
                rejected_date=rejected_date,
            )

            lines.append(
                {
                    'name': name,
                    'quantity': 1,
                    'price_unit': check.amount,
                    'account_id': account_id,
                }
            )

            # Lineas de gastos
            for expense in self.expense_line_ids:
                product = expense.product_id
                account_id = product.property_account_expense_id
                if not account_id:
                    account_id = (
                        product.categ_id.property_account_expense_categ_id
                    )
                if not account_id:
                    raise ValidationError(
                        _('Please, fill the expense account in the product.')
                    )

                lines.append(
                    {
                        'name': expense.product_id.name,
                        'product_id': expense.product_id.id,
                        'quantity': 1,
                        'price_unit': expense.price,
                        'account_id': account_id.id,
                        'tax_ids': [(6, 0, expense.product_id.taxes_id.ids)],
                    }
                )

            invoice_vals['invoice_line_ids'] = [(0, 0, line) for line in lines]

            # creamos la nota de debito
            debit_note_id = self.env['account.move'].create(invoice_vals)
            debit_note_id._onchange_partner_id()

            # Volvemos a cambiar la cuenta que sobreescribio el onchange
            # debit_note_id.account_id = inv_account_id
            debit_note_id._onchange_invoice_line_ids()

            # Hay que actualizar el campo 'is_debit_note' porque se computa como False:
            debit_note_id.write({'is_debit_note': True})

        if check.third_party_check_state in ('delivered', 'deposited'):
            # Guardamos la referencia a la nota de debito del rechazo y cambiamos el estado
            check.write(
                {
                    'third_party_check_state': 'rejected',
                    'debit_note_id': debit_note_id.id,
                }
            )

        form_res = self.env.ref(
            'l10n_ar_eynes.account_move_view_form_inherit_l10n_ar_eynes'
        )
        form_id = form_res and form_res.id or False
        tree_res = self.env.ref(
            'l10n_ar_eynes.account_move_view_tree_inherit_l10n_ar_eynes'
        )
        tree_id = tree_res and tree_res.id or False

        return {
            'name': _('Invoice'),
            'view_mode': 'form,tree',
            'res_model': 'account.move',
            'res_id': debit_note_id.id,
            'view_id': False,
            'views': [(form_id, 'form'), (tree_id, 'tree')],
            'type': 'ir.actions.act_window',
        }

    def get_account(self, config, check):
        """
        Return account based on check state

        Args:
            config (account.check.config): company check configuration
            check (account.third.party.check): 3rd party check

        Returns:
            account.account: Returns account object
        """
        account_id = False
        state = check.third_party_check_state
        if state == 'delivered':
            account_id = config.rejected_account_id.id
        elif state == 'deposited':
            account_id = check.deposit_bank_id.account_id.id
        elif state == 'in_wallet':
            account_id = config.account_id.id
        return account_id


class CheckRejectExpense(models.TransientModel):
    _name = 'check.reject.expense'
    _description = 'Reject Expense'

    reject_id = fields.Many2one(
        comodel_name='reject.third.party.check.wizard', string='Reject'
    )
    product_id = fields.Many2one(
        comodel_name='product.product', string='Product', required=True
    )
    price = fields.Float(string='Amount', digits='Account', required=True)
