from odoo import fields, models


class AccountPaymentMethodLine(models.Model):
    _inherit = 'account.payment.method.line'

    format = fields.Selection(
        selection=[('physical', 'Physical'), ('virtual', 'Virtual'), ('echeq', 'Echeq')],
        string='Format',
    )
