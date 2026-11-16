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
        return self.env.context.get("active_id", False)

    def _get_checks_to_debit(self):
        """Checks the wizard is going to operate on"""
        if self.multichecks:
            return self.issued_checks
        return self.issued_check_id

    def button_debit_checks(self):
        """button that run debit checks action"""
        if not self.deposit_date:
            raise UserError(_('You must select a deposit date.'))
        checks = self._get_checks_to_debit()
        if not checks:
            raise UserError(_("You must select at least one check."))
        return checks.debit_checks(self.deposit_date)
