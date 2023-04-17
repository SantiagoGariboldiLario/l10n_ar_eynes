from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AccountMove(models.Model):
    _inherit = 'account.move'

    denomination = fields.Selection(
        selection=[
            ("a", "A"),
            ("b", "B"),
            ("c", "C"),
            ("e", "E"),
            ('m', 'M'),
            ('oc', 'OC'),
            ("not_defined", "Not Defined"),
        ],
        string='Denomination',
    )
    supplier_move_reference = fields.Char(string='Supplier Invoice Reference')
    address_shipping_id = fields.Many2one(
        comodel_name='res.partner',
        name='Shipping Address',
        readonly=True,
        required=False,
        states={
            'draft': [('readonly', False)],
        },
    )
    is_debit_note = fields.Boolean(string='Debit Note', default=False)

    def get_highest_pos_sequence(self):
        invoices = self.env['account.move'].search(
            [
                ('journal_id', '=', self.journal_id.id),
                ('move_type', '=', self.move_type),
                ('is_debit_note', '=', self.is_debit_note),
            ]
        )

        if not invoices or len(invoices) == 1:
            return '1'.zfill(8)

        last_sequence_number = max(invoices.mapped('sequence_number'))
        return str(last_sequence_number + 1).zfill(8)

    # ONCHANGE METHODS
    @api.onchange('journal_id', 'partner_id')
    def _onchange_journal(self):
        if not self.partner_id:
            return
        if self.journal_id.type == 'sale':
            super(AccountMove, self)._onchange_journal()
            self.denomination = self.journal_id.denomination

    @api.onchange('partner_id')
    def _onchange_partner(self):
        if not self.partner_id:
            return
        super(AccountMove, self)._onchange_partner_id()
        if self.is_sale_document():
            partner_fiscal_position = self.partner_id.property_account_position_id
            journals = self.env.user.journal_ids.filtered(
                lambda j: partner_fiscal_position in j.fiscal_position_ids
            )
            if journals:
                self.journal_id = journals[0]
                self._onchange_journal()
                return {'domain': {'journal_id': [('id', 'in', journals.ids)]}}

    @api.onchange(
        'supplier_move_reference', 'denomination', 'fiscal_position_id', 'partner_id'
    )
    def _onchange_supplier_move_reference(self):
        if not self.supplier_move_reference:
            return

        # Separator missing or multiple separators error
        if self.supplier_move_reference.count('-') != 1:
            raise ValidationError(_('Must be only one separator'))

        pos_code, move_code = self.supplier_move_reference.split('-')
        if not pos_code or not move_code:
            raise ValidationError(_('numbers missing after or before separator'))
        if not pos_code.isnumeric() or not move_code.isnumeric():
            raise ValidationError(_('the reference must be numbers only'))
        if len(pos_code) > 5 or len(move_code) > 8:
            raise ValidationError(_('Some of the fields exceeds length'))

        self.supplier_move_reference = pos_code.zfill(4) + '-' + move_code.zfill(8)
        self.name = self.supplier_move_reference

    @api.onchange('fiscal_position_id', 'partner_id')
    def _onchange_fiscal_position(self):
        fiscal_position = (
            self.fiscal_position_id or self.partner_id.property_account_position_id
        )
        if self.is_purchase_document():
            self.denomination = fiscal_position.supplier_denomination

    def action_post(self):
        if self.is_sale_document():
            if self.id:
                self.validate_denomination()
                self.validate_period()
                if not self.payment_reference:
                    self.write(
                        {
                            'name': f'{self.journal_id.code}-{self.get_highest_pos_sequence()}',
                        }
                    )
        return super(AccountMove, self).action_post()

    def validate_period(self):
        date = self.invoice_date or fields.Date.context_today(self)
        if not self.journal_id.due_date:
            raise ValidationError(
                _(
                    "The journal does not have a period established\n"
                    "Please add a period in: "
                    "accounting/journals/update journals periods"
                )
            )
        if date < self.journal_id.due_date:
            raise ValidationError(
                _(
                    "You are trying to create an invoice with a date older date "
                    "than the allowed by the journal"
                )
            )

    def validate_denomination(self):
        if not self.denomination or self.denomination == 'not_defined':
            raise ValidationError(_("Invoice must have a denomination configured"))

    @api.model_create_multi
    def create(self, vals):
        res = super().create(vals)
        for move in res.filtered(lambda m: m.is_sale_document()):
            if not move.denomination:
                move.write({'denomination': move.journal_id.denomination})
        return res

    def action_register_payment(self):
        """Override to redirect to account payment order"""
        po = self.env['account.payment.order'].create(self.get_payment_order_vals())

        if self.is_sale_document():
            view_id = self.env.ref(
                'l10n_ar_eynes.account_customer_payment_order_view_form'
            )
        else:
            view_id = self.env.ref(
                'l10n_ar_eynes.account_supplier_payment_order_view_form'
            )
        return {
            'name': _('Customer Payment'),
            'res_model': 'account.payment.order',
            'res_id': po.id,
            'view_mode': 'form',
            'view_id': view_id.id,
            'target': 'current',
            'type': 'ir.actions.act_window',
        }

    def get_payment_order_vals(self):
        move_line_domain = [('id', 'in', self.line_ids.ids), ('reconciled', '=', False)]
        if self.is_sale_document():
            move_line_domain += [
                ('debit', '>', 0),
                ('credit', '=', 0),
            ]
        else:
            move_line_domain += [
                ('debit', '=', 0),
                ('credit', '>', 0),
            ]
        move_line = self.env['account.move.line'].search(move_line_domain)
        po_move_line = [
            (
                0,
                0,
                {
                    'invoice_id': self.id,
                    'move_line_id': move_line.id,
                    'account_id': move_line.account_id.id,
                },
            )
        ]

        po_vals = {
            'type': 'receipt' if self.is_sale_document() else 'payment',
            'partner_id': self.partner_id.id,
            'journal_id': self.get_receipt_journal().id
            if self.is_sale_document()
            else self.get_payment_journal().id,
        }

        if self.is_sale_document():
            po_vals['income_line_ids'] = po_move_line
        else:
            po_vals['debt_line_ids'] = po_move_line
        return po_vals

    def get_payment_journal(self):
        return self.env['account.journal'].search([('type', '=', 'payment')])[0]

    def get_receipt_journal(self):
        return self.env['account.journal'].search([('type', '=', 'receipt')])[0]

    @api.constrains('name', 'journal_id', 'state')
    def _check_unique_sequence_number(self):
        moves = self.filtered(lambda move: move.state == 'posted')
        if not moves:
            return

        self.flush(['name', 'journal_id', 'move_type', 'state'])

        # /!\ Computed stored fields are not yet inside the database.
        self._cr.execute(
            '''
            SELECT move2.id, move2.name
            FROM account_move move
            INNER JOIN account_move move2 ON
                move2.name = move.name
                AND move2.journal_id = move.journal_id
                AND move2.move_type = move.move_type
                AND move2.is_debit_note = move.is_debit_note
                AND move2.id != move.id
            WHERE move.id IN %s AND move2.state = 'posted'
        ''',
            [tuple(moves.ids)],
        )
        res = self._cr.fetchall()
        if res:
            raise ValidationError(
                _(
                    'Posted journal entry must have an unique sequence number per company.\n'
                    'Problematic numbers: %s\n'
                )
                % ', '.join(r[1] for r in res)
            )

    _sql_constraints = [
        (
            'unique_move',
            'unique(partner_id, supplier_move_reference, is_debit_note)',
            _('This invoice reference already exists for this supplier'),
        ),
    ]


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    issued_check_id = fields.Many2one(
        comodel_name='account.check',
        string='Issued Check',
        domain=[('internal_type', '=', 'issued')],
    )
    counterpart = fields.Char(
        "Counterpart",
        compute='_compute_counterpart',
        help="Compute the counter part accounts of "
        "this journal item for this journal entry. This can be needed in reports.",
    )

    @api.depends('move_id.line_ids')
    def _compute_counterpart(self):
        for rec in self:
            counterpart = set()
            for line in rec.move_id.line_ids:
                if line.account_id.code != rec.account_id.code:
                    counterpart.add(line.account_id.code)
            if len(counterpart) > 2:
                counterpart = list(counterpart)[0:2] + ["..."]
            self.counterpart = ",".join(counterpart)
