from odoo import api, models, fields


class AccountMove(models.Model):
    _inherit = 'account.move'
    _name = 'account.move'
    _description = "Account Move"

    denomination = fields.Selection(string="Denomination", related='journal_id.denomination')

    def get_highest_pos_sequence(self):
        print(self.journal_id)
        invoices = self.env['account.move'].search([('journal_id', '=', self.journal_id.id)])
        if not invoices:
            return '00000001'

        last_sequence_number = max([inv.sequence_number for inv in invoices])
        number_of_zeros = 8 - len(str(last_sequence_number + 1))
        return '0' * number_of_zeros + str(last_sequence_number + 1)

# ONCHANGE METHODS
    @api.onchange('journal_id')
    def onchange_journal_id(self):
        super(AccountMove, self)._onchange_journal()
        if self.journal_id.code.isnumeric:
            self.name = self.journal_id.code + '-' + self.get_highest_pos_sequence()
        self.fiscal_position_id = self.journal_id.fiscal_position_id

    @api.onchange('partner_id')
    def onchange_partner_id(self):
        super(AccountMove, self)._onchange_partner_id()
        self.onchange_journal_id()
