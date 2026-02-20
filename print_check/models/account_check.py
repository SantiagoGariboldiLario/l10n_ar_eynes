from odoo import fields, models


class AccountCheck(models.Model):
    _inherit = 'account.check'
    _description = 'Account Check'

    check_printed = fields.Boolean(string='Check Printed', default=False)
