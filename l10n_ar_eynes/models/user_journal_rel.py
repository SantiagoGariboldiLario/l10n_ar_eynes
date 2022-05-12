from odoo import models, fields, _


class UserJournalRel(models.Model):
    _name = 'user.journal.rel'
    _description = 'User Journal Relation'

    def get_last_sequence(self):
        relations = self.env['user.journal.rel'].search([])
        if relations:
            return max(map(lambda rec: rec.sequence, relations)) + 1
        return 1

    user_id = fields.Many2one(
        string='User',
        comodel_name='res.users',
        ondelete='cascade'
    )
    journal_id = fields.Many2one(
        string='Journal',
        comodel_name='account.journal',
        ondelete='cascade',
        domain="[('type','=','sale')]"
    )
    sequence = fields.Integer(
        string="Sequence",
        default=get_last_sequence,
        readonly=True
    )

    _sql_constraints = [
        (
            'unique_combination', 'unique(user_id,journal_id)', _('User already assigned to this journal!'))
    ]
