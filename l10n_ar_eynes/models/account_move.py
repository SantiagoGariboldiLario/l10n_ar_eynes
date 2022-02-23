from odoo import api, models, fields
from odoo.exceptions import ValidationError


class AccountMove(models.Model):
    _inherit = 'account.move'
    _name = 'account.move'
    _description = "Account Move"

    denomination = fields.Selection(
        [("a", "A"), ("b", "B"), ("c", "C"), ("e", "E"), ("not_defined", "Not Defined")],
        string='Denomination',
        default='not_defined'
    )
    supplier_move_reference = fields.Char(string='Supplier Invoivce Reference', size=14)

    def get_highest_pos_sequence(self):
        invoices = self.env['account.move'].search([('journal_id', '=', self.journal_id.id)])

        if not invoices:
            return '1'.zfill(8)

        last_sequence_number = max([inv.sequence_number for inv in invoices])
        return str(last_sequence_number + 1).zfill(8)

# ONCHANGE METHODS
    @api.onchange('journal_id')
    def _onchange_journal(self):
        super(AccountMove, self)._onchange_journal()
        if self.journal_id.type == 'sale':
            if self.journal_id.code.isnumeric:
                self.name = self.journal_id.code + '-' + self.get_highest_pos_sequence()

    @api.onchange('partner_id')
    def _onchange_partner(self):
        if (not self.partner_id) or (self.move_type == 'in_invoice'):
            return
        super(AccountMove, self)._onchange_partner_id()
        relations = self.env['user.journal.rel'].search(
            [
                ('journal_id.fiscal_position_id', '=', self.fiscal_position_id.id),
                ('user_id', '=', self.env.user.id)
            ],
            order='sequence asc',
        )
        if relations:
            ids = list(map(lambda relation: relation.journal_id.id, relations))
            domain = {'journal_id' : [('id', 'in', ids)]}
            self.journal_id = relations[0].journal_id
            self.onchange_journal_id()
            return{
                'domain' : domain,
            }

    @api.onchange('supplier_move_reference')
    def _onchange_supplier_move_reference(self):
        if not self.supplier_move_reference:
            return

        # Separator missing or multiple separators error
        if self.supplier_move_reference.count('-') != 1:
            raise ValidationError('Must be only one separator')

        pos_code, move_code = self.supplier_move_reference.split('-')
        if not pos_code or not move_code:
            raise ValidationError('numbers missing after or before separator')
        if not pos_code.isnumeric() or not move_code.isnumeric():
            raise ValidationError('the reference must be numbers only')
        if len(pos_code) > 5 or len(move_code) > 8:
            raise ValidationError('Some of the fields exceeds length')

        self.supplier_move_reference = pos_code.zfill(5) + '-' + move_code.zfill(8)
        self.name = f'{self.supplier_move_reference}'

        if self.denomination != 'not_defined':
            self.name = f'{self.denomination.capitalize()} {self.name}'

    @api.onchange('denomination')
    def _onchange_denomination(self):
        self._onchange_supplier_move_reference()

    _sql_constraints = [
        ('unique_move', 'unique(journal_id,supplier_move_reference)', 'move already exists!'),
        ('unique_name', 'unique(name)', 'move already exists!')
    ]
