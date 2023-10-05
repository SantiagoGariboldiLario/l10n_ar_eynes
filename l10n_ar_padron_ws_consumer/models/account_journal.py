from odoo import fields, models


class AccountJournal(models.Model):
    _inherit = "account.journal"

    padron_state_id = fields.Many2one(
        'res.country.state',
        string='Padron State to apply',
    )
