from odoo import _, api, fields, models
from odoo.exceptions import UserError


class DebitCheckWizard(models.Model):
    _name = 'debit.check.wizard'
    _description = 'Select several checks which are Waiting debitation so you can debit them'

    deposit_date = fields.Date()
    issued_checks = fields.Many2many(
        comodel_name='account.check',
        default=lambda self: self._get_default_checks(),
    )
    issued_check_id = fields.Many2one(
        'account.check',
        default=lambda self: self._get_issued_check_id(),
        readonly=True,
    )
    multichecks = fields.Boolean(
        default=lambda self: self._get_default_method()
    )

    @api.model
    def _get_default_checks(self):
        """Get active checks"""
        check_ids = self.env.context.get("active_ids", [])
        return [(6, False, check_ids)]

    @api.model
    def _get_default_method(self):
        return not self.env.context.get("one_check", False)

    @api.model
    def _get_issued_check_id(self):
        return self.env.context.get("active_id", [])

    def button_debit_checks(self):
        """button that run debit checks action"""
        if not self.deposit_date:
            raise UserError(_('You must select a deposit date.'))
        return self.issued_checks.debit_checks(self.deposit_date)
