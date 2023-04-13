from odoo import models, fields, _, api


class UserJournalRel(models.Model):
    _name = 'user.journal.rel'
    _description = 'User Journal Relation'

    def get_last_sequence(self):
        relations = self.env['user.journal.rel'].search([])
        if relations:
            return max(map(lambda rec: rec.sequence, relations)) + 1
        return 1

    user_id = fields.Many2one(string='User', comodel_name='res.users', ondelete='cascade')
    journal_id = fields.Many2one(
        string='Journal',
        comodel_name='account.journal',
        ondelete='cascade',
        domain="[('type','=','sale')]",
    )
    sequence = fields.Integer(string="Sequence", default=get_last_sequence, readonly=True)

    @api.model
    def get_first_journal(self, partner):
        first_relation_seq = self.search(
            [
                (
                    'journal_id.fiscal_position_id',
                    '=',
                    partner.property_account_position_id.id,
                ),
                ('user_id', '=', self.env.user.id),
            ],
            order='sequence asc',
            limit=1,
        )
        return first_relation_seq.journal_id or False

    _sql_constraints = [
        (
            'unique_combination',
            'unique(user_id,journal_id)',
            _('User already assigned to this journal!'),
        )
    ]
