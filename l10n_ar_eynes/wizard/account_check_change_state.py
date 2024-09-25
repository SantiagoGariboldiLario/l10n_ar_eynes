import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ChangeCheckStateWizard(models.TransientModel):
    _name = 'change.check.state.wizard'
    _description = 'Change Check State'

    check_id = fields.Many2one(
        comodel_name='account.check',
        default=lambda self: self._get_default_check(),
    )
    new_state = fields.Selection(selection=lambda self: self._load_options())
    reason = fields.Text()

    def _load_options(self):
        check_id = self.env.context.get("active_ids", False)
        Check = self.env['account.check']

        if check_id and len(check_id) == 1:
            account_check = Check.browse(check_id)
            if account_check.internal_type == 'issued':
                if account_check.issued_check_state == 'draft':
                    return [
                        ('cancelled', 'Cancelled'),
                    ]
                if account_check.issued_check_state == 'waiting_debit':
                    return [
                        ('expired', 'Expired'),
                    ]
            elif account_check.internal_type == 'third_party':
                if account_check.third_party_check_state == 'in_wallet':
                    return [
                        ('expired', 'Expired'),
                    ]

        return [
            ('cancelled', 'Cancelled'),
            ('expired', 'Expired'),
        ]

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
        if not self.check_id:
            raise UserError(_('You must select a check.'))

        if self.new_state == 'cancelled':
            return self.check_id.cancel_check(self.reason)
        if self.new_state == 'expired':
            return self.check_id.expired_check(self.reason)
