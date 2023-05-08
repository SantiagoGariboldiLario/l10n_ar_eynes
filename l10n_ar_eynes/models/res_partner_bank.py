from odoo import fields, models


class ResParterBank(models.Model):
    _inherit = 'res.partner.bank'

    account_id = fields.Many2one(
        comodel_name='account.account',
        string='Account',
    )
