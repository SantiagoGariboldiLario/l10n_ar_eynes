from odoo import fields, models, _
from odoo.addons import decimal_precision as dp
from odoo.exceptions import ValidationError, UserError


class RejectIssuedCheckWizard(models.TransientModel):
    _name = 'reject.issued.check.wizard'
    _description = 'Reject issued check wizard'

    def get_default_journal(self):
        return self.env.user.company_id.rejected_issued_checks_journal_id.id \
            or False

    reject_date = fields.Date(string='Reject date')
    note = fields.Text(string='Note')
    generate_rejection_journal_entry = fields.Boolean(
        string='Generate Rejection Journal Entry',
        default=True
    )

    def action_reject(self):
        """
        This method is called when the rejection is confirmed in the wizard.
        It change the state of the check to 'rejected' and also creates a move.
        """
        self.validate_journal()

        check = self.env['account.check'].browse(
            self._context.get('active_id')  # active check_id
        )
        if check:
            check.write({
                'reject_date': self.reject_date,
                'note': self.note
            })
            if self.generate_rejection_journal_entry:
                self.generate_rejection_journal_entry(check)

            check.write({
                'issued_check_state' : 'rejected'
            })

    def generate_rejection_journal_entry(self, check):
        """
        This method generates an invoice which register the
        check rejection as an invoice movement. It also adds the lines to the payment order

        Args:
            check (_type_): check record
        """
        # object models
        move_obj = self.env['account.move']
        move_line_obj = self.env['account.move.line']
        account_obj = self.env['account.account']

        journal = self.env.user.company_id.rejected_issued_checks_journal_id
        payment = check.payment_order_id

        def_check_account = self.env['account.check.config'].search([
            ('company_id', '=', self.env.user.company_id.id)
        ]).deferred_account_id.id

        ctx = {
            'date': self.reject_date,
            'check_move_validity': False,
        }

        for payment_line in payment.move_line_ids:
            if payment_line.issued_check_id == check:
                original_move_data = payment.account_move_get()
                original_move_data['journal_id'] = journal.id
                original_move_data['state'] = 'posted'
                move_recordset = move_obj.with_context(ctx).create(
                    original_move_data
                )

            # Get the name of the account_move just created
                move_id = move_recordset.id
                counterpart_account = account_obj.search([
                    ('code', '=', payment_line.counterpart)
                ]).id

                inverse_supplier_line = {
                    'name': '/',
                    'account_id': counterpart_account,
                    'move_id': move_id,
                    'partner_id': payment_line.partner_id.id,
                    'date': self.reject_date,
                    'credit': payment_line.credit,
                    'debit': 0,
                    'amount_currency': payment_line.amount_currency,
                    'journal_id': original_move_data['journal_id'],
                    'currency_id': payment_line.currency_id.id,
                    'analytic_account_id': payment_line.analytic_account_id.id,
                    'ref': _('Rejected check') + ': ' + (payment_line.name or '/'),
                }
                move_line_obj.with_context(ctx).create(inverse_supplier_line)

                inverse_check_line = {
                    'name': _('Rejected check') + ': ' + (payment_line.name or '/'),
                    'account_id': def_check_account,
                    'move_id': move_id,
                    'partner_id': payment_line.partner_id.id,
                    'date': self.reject_date,
                    'credit': 0,
                    'debit': payment_line.credit,
                    'amount_currency': payment_line.amount_currency,
                    'journal_id': original_move_data['journal_id'],
                    'currency_id': payment_line.currency_id.id,
                    'analytic_account_id': payment_line.analytic_account_id.id,
                    'ref': _('Rejected check') + ': ' + (payment_line.name or '/'),
                }
                move_line_obj.with_context(ctx).create(inverse_check_line)

    def validate_journal(self):
        """
        This methods checks that the journal field is not empty.
        The journal in the model is loaded by default from the company reject issued check journal.
        If the default journal is not loaded it raise an error explaining this.
        """
        if not self.env.user.company_id.rejected_issued_checks_journal_id:
            raise UserError(
                _("No default journal configured yet.\n"
                  + "Journal reject issued checks configuration is needed.\n"
                  + "To do that go to Invoicing/configuration/settings/journals ")
            )


class RejectThirdPartyCheckWizard(models.TransientModel):
    _name = 'reject.third.party.check.wizard'
    _description = 'Reject third party check wizard'

    reject_date = fields.Date('Reject date')
    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Journal',
        required=True,
        default='_get_journal'
    )
    expense_line_ids = fields.One2many(
        comodel_name='check.reject.expense',
        inverse_name='reject_id',
        string='Expenses'
    )

    def _get_journal(self):
        user = self.env.user
        company_id = self.env.context.get('company_id', user.company_id.id)
        journal = self.env['account.journal'].search(
            [('company_id', '=', company_id), ('type', '=', 'sale')],
            limit=1
        )
        return journal and journal.id or False

    def action_reject(self):

        # object models
        check_config_obj = self.env['account.check.config']
        check_obj = self.env['account.check']
        invoice_obj = self.env['account.move']

        record_id = self._context.get('active_id')
        check = check_obj.browse(record_id)

        if check:
            check.reject_date = self.reject_date
            partner = check.source_partner_id

            config = check_config_obj.search([
                ('company_id', '=', check.company_id.id)
            ])
            if not config:
                raise ValidationError(
                    _('ERROR! There is no check configuration for this Company!')
                )

            inv_account_id = config.receivable_rejected_account_id
            if not inv_account_id:
                inv_account_id = partner.property_account_receivable_id

            name = _('Debit Note due to rejected check %s [%s]') \
                % (check.number or '', check.source_payment_order_id.number)
            invoice_vals = {
                'origin': _('Check : %s') % check.number,
                'name': name,
                'type': 'out_invoice',
                'is_debit_note': True,
                'account_id': inv_account_id.id,
                'partner_id': partner.id,
                'journal_id': self.journal_id.id,
                'fiscal_position': partner.property_account_position_id.id,
                'company_id': self.company_id.id,
            }

            lines = []
            # Linea del cheque rechazado

            account_id = False
            if check.state == 'delivered':
                account_id = config.rejected_account_id.id
            elif check.state == 'deposited':
                account_id = check.deposit_bank_id.account_id.id
            elif check.state == 'in_wallet':
                account_id = config.account_id.id

            date_format = self.env["res.lang"].search([
                ("code", "=", self.env.user.lang)
            ]).date_format

            rejected_date = self.reject_date.strftime(date_format)
            name = _('Check Rejected %s %s') % (check.number, rejected_date)

            lines.append((0, 0, {
                'name': name,
                'quantity': 1,
                'price_unit': check.amount,
                'account_id': account_id,
            }))

            # Lineas de gastos
            for expense in self.expense_line_ids:

                product = expense.product_id
                account_id = product.property_account_expense_id
                if not account_id:
                    account_id = product.categ_id.\
                        property_account_expense_categ_id
                if not account_id:
                    raise ValidationError(
                        _('Please, fill the expense account in the product.')
                    )

                lines.append((0, 0, {
                    'name': expense.product_id.name,
                    'product_id': expense.product_id.id,
                    'quantity': 1,
                    'price_unit': expense.price,
                    'account_id': account_id.id,
                    'invoice_line_tax_ids': [
                        (6, 0, expense.product_id.taxes_id.ids)
                    ],
                }))

            debit_note_id = invoice_obj.create(invoice_vals)
            debit_note_id._onchange_partner_id()

            # Volvemos a cambiar la cuenta que sobreescribio el onchange
            debit_note_id.account_id = inv_account_id
            debit_note_id._onchange_invoice_line_ids()

        if check.third_party_check_state in ('delivered', 'deposited'):
            check.write({
                'third_party_check_state' : 'rejected'
            })

        # Guardamos la referencia a la nota de debito del rechazo
        check.third_party_check_state = 'rejected'
        check.debit_note_id = debit_note_id

        form_res = self.env.ref(
            'l10n_ar_eynes.account_move_view_form_inherit_l10n_ar_eynes'
        )
        form_id = form_res and form_res.id or False
        tree_res = self.env.ref('base.view_move_tree')
        tree_id = tree_res and tree_res.id or False

        return {
            'name': _('Invoice'),
            'view_type': 'form',
            'view_mode': 'form,tree',
            'res_model': 'account.move',
            'res_id': debit_note_id.id,
            'view_id': False,
            'views': [(form_id, 'form'), (tree_id, 'tree')],
            'type': 'ir.actions.act_window',
        }


class CheckRejectExpense(models.TransientModel):
    _name = 'check.reject.expense'
    _description = 'Reject Expense'

    reject_id = fields.Many2one(
        comodel_name='reject.third.party.check.wizard',
        string='Reject'
    )
    product_id = fields.Many2one(
        comodel_name='product.product',
        string='Product',
        required=True
    )
    price = fields.Float(
        string='Amount',
        digits=dp.get_precision('Account'),
        required=True
    )
