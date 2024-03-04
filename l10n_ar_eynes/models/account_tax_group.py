from odoo import fields, models


class AccountTaxGroup(models.Model):
    _inherit = 'account.tax.group'

    group_type = fields.Selection(
        [
            ('vat', 'Vat'),
            ('perception', 'Perception'),
            ('retention', 'Retention'),
            ('internals', 'Internals'),
            ('others', 'Others'),
        ]
    )
