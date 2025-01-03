from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResUsers(models.Model):
    _inherit = "res.users"

    journal_rel_ids = fields.One2many(
        comodel_name='users.journals.priority.rel',
        inverse_name='user_id',
        string='Available Point of Sales Journals',
    )
    used_journals_domain = fields.Binary(
        compute='_compute_used_journals_domain'
    )

    def get_journals_by_fiscal_position(self, fiscal_position):
        return self.journal_rel_ids.journal_id.filtered(
            lambda j: fiscal_position in j.fiscal_position_ids
        )

    @api.depends('journal_rel_ids')
    def _compute_used_journals_domain(self):
        for rec in self:
            domain = [('type', '=', 'sale')]
            if rec.journal_rel_ids:
                domain.append(
                    (
                        'id',
                        'not in',
                        rec.journal_rel_ids.mapped('journal_id').ids,
                    )
                )
            rec.used_journals_domain = domain


class UsersJournalPriorityRel(models.Model):
    _name = 'users.journals.priority.rel'
    _order = 'priority asc'

    code = fields.Char(string='POS code', related='journal_id.code')
    company_id = fields.Many2one(related='journal_id.company_id')
    journal_id = fields.Many2one(
        comodel_name='account.journal',
    )
    used_journals_domain = fields.Binary(related='user_id.used_journals_domain')
    user_id = fields.Many2one(
        comodel_name='res.users',
    )
    priority = fields.Integer(readonly=True)

    @api.constrains('user_id', 'journal_id')
    def _check_one_journal(self):
        for record in self:
            user_records = (
                self.env['users.journals.priority.rel']
                .sudo()
                .search(
                    [
                        ('user_id', '=', record.user_id.id),
                        ('journal_id', '=', record.journal_id.id),
                        ('id', '!=', record.id),
                    ]
                )
            )

            if user_records:
                raise ValidationError(
                    _(
                        '%(username)s already has this journal (%(journal)s) configured.',
                        username=record.user_id.name,
                        journal=record.journal_id.name,
                    )
                )

    def create(self, vals):
        last_user_record = self.env['users.journals.priority.rel'].search(
            [('user_id', '=', vals[0]['user_id'])],
            order='priority desc',
            limit=1,
        )
        last_user_priority = last_user_record.priority
        for val in vals:
            last_user_priority += 1
            val.update({'priority': last_user_priority})

        return super(UsersJournalPriorityRel, self).create(vals)

    def _recompute_user_priorities(self, users):
        for user in users:
            user_records = self.env['users.journals.priority.rel'].search(
                [('user_id', '=', user.id)], order='priority asc'
            )
            priority = 1
            for record in user_records:
                record.priority = priority
                priority += 1

    def unlink(self):
        users = self.mapped('user_id')
        res = super().unlink()
        self._recompute_user_priorities(users)
        return res
