from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    journal_ids = fields.Many2many(
        comodel_name='account.journal',
        relation='users_journals_rel',
        column1='user_id',
        column2='journal_id',
        string='Available Journals',
        domain=[('type', '=', 'sale')],
    )
    # journal_id = fields.Many2one(
    #     comodel_name='account.journal',
    #     string='Default POS',
    # )
