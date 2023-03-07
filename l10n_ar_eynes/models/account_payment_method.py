from odoo import fields, models, _


class AccountPaymentMethodLine(models.Model):
    _inherit = 'account.payment.method.line'

    number = fields.Integer('number')
    format = fields.Selection(
        selection=[
            ('physical', 'Physical'),
            ('virtual', 'Virtual'),
            ('echeq', 'Echeq')
        ],
        string='Format',
    )

    _sql_constraints = [
        (
            "unique_checkbook",
            "unique(journal_id, format, number)",
            _("This checkbook already exists for this journal")
        ),
    ]
