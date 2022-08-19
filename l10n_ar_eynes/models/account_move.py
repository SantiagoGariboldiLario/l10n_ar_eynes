from odoo import api, models, fields, _
from odoo.exceptions import ValidationError


class AccountMove(models.Model):
    _inherit = 'account.move'

    denomination = fields.Selection(
        selection=[
            ("a", "A"), ("b", "B"),
            ("c", "C"), ("e", "E"),
            ("not_defined", "Not Defined")
        ],
        string='Denomination',
    )
    supplier_move_reference = fields.Char(string='Supplier Invoice Reference')

    def get_highest_pos_sequence(self):
        invoices = self.env['account.move'].search([
            ('journal_id', '=', self.journal_id.id)
        ])

        if not invoices:
            return '1'.zfill(8)

        last_sequence_number = max([inv.sequence_number for inv in invoices])
        return str(last_sequence_number + 1).zfill(8)

# ONCHANGE METHODS
    @api.onchange('journal_id', 'partner_id')
    def _onchange_journal(self):
        if not self.partner_id:
            return
        if self.journal_id.type == 'sale':
            super(AccountMove, self)._onchange_journal()
            self.denomination = self.journal_id.denomination
            if self.journal_id.code.isnumeric:
                self.update_name()

    @api.onchange('partner_id')
    def _onchange_partner(self):
        if not self.partner_id:
            return
        super(AccountMove, self)._onchange_partner_id()
        if self.move_type == 'out_invoice':
            relations = self.env['user.journal.rel'].search([
                ('journal_id.fiscal_position_id', '=', self.fiscal_position_id.id),
                ('user_id', '=', self.env.user.id)],
                order='sequence asc',
            )
            if relations:
                ids = list(map(lambda relation: relation.journal_id.id, relations))
                domain = {'journal_id' : [('id', 'in', ids)]}
                self.journal_id = relations[0].journal_id
                self._onchange_journal()
                return {
                    'domain' : domain,
                }

    @api.onchange('supplier_move_reference', 'denomination',
                  'fiscal_position_id', 'partner_id')
    def _onchange_supplier_move_reference(self):
        if not self.supplier_move_reference:
            return

        # Separator missing or multiple separators error
        if self.supplier_move_reference.count('-') != 1:
            raise ValidationError('Must be only one separator')

        pos_code, move_code = self.supplier_move_reference.split('-')
        if not pos_code or not move_code:
            raise ValidationError(
                _('numbers missing after or before separator')
            )
        if not pos_code.isnumeric() or not move_code.isnumeric():
            raise ValidationError(
                _('the reference must be numbers only')
            )
        if len(pos_code) > 5 or len(move_code) > 8:
            raise ValidationError(
                _('Some of the fields exceeds length')
            )

        self.supplier_move_reference = pos_code.zfill(4) \
            + '-' + move_code.zfill(8)
        self.name = f'{self.supplier_move_reference}'

        if self.denomination and self.denomination != 'not_defined':
            self.name = f'{self.denomination.capitalize()} {self.name}'

    @api.onchange('fiscal_position_id', 'partner_id')
    def _onchange_fiscal_position(self):
        fiscal_position = self.fiscal_position_id \
            or self.partner_id.property_account_position_id
        if self.move_type == 'in_invoice':
            self.denomination = fiscal_position.supplier_denomination

    # def action_post(self):
    #     if not self.journal_id.due_date:
    #         raise ValidationError(
    #             _("This journal Does not have a period established.\n"
    #               + "Please Establish period before moving on.\n"
    #               + "This can be accomplished in \
    #               Accounting/Journals/Update Journals Period")
    #         )
    #     elif self.journal_id.due_date < fields.Date.today():
    #         raise ValidationError(
    #             _("Journal period date has expired.\n"
    #               + "Change journal or update period expiration date")
    #         )
    #     super(AccountMove, self).action_post()

    def update_name(self):
        denomination = self.denomination.capitalize()
        code = self.journal_id.code
        sequence = self.get_highest_pos_sequence()
        self.name = f'{denomination}{code}-{sequence}'

    _sql_constraints = [
        (
            'unique_move',
            'unique(journal_id,supplier_move_reference)',
            _('move already exists!')
        ),
        (
            'unique_name',
            'unique(name)',
            _('move already exists!')
        )
    ]


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    issued_check_id = fields.Many2one(
        comodel_name='account.check',
        string='Issued Check',
        domain=[('internal_type', '=', 'issued')]
    )
