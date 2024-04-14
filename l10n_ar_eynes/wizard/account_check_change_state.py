import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ChangeCheckStateWizard(models.TransientModel):
    _name = 'change.check.state.wizard'
    _description = 'Change Check State'

    issued_check = fields.Many2one(
        comodel_name='account.check',
        default=lambda self: self._get_default_check(),
    )
    new_state = fields.Selection(
        selection=[
            ('cancelled', 'Cancelled'),
            ('expired', 'Expired'),
        ]
    )
    reason = fields.Text()

    @api.model
    def _get_default_check(self):
        """Get active check"""
        check_id = self.env.context.get("active_ids", [])
        Check = self.env['account.check']
        if len(check_id) != 1:
            return Check
        return Check.browse(check_id)

    def change_stage(self):
        if not self.new_state:
            raise UserError(_('You must select the new state for this check.'))
        if not self.issued_check:
            raise UserError(_('You must select a check.'))

        if self.new_state == 'cancelled':
            if self.issued_check.internal_type == 'issued':
                return self.issued_check.cancel_check(internal_type='issued')
            else:
                return self.issued_check.cancel_check(
                    internal_type='third_party'
                )
        if self.new_state == 'expired':
            return self.issued_check.expired_check()
