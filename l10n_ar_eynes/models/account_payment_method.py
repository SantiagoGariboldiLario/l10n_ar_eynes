from odoo import _, api, fields, models


class AccountPaymentMethod(models.Model):
    _inherit = 'account.payment.method'

    @api.model
    def _get_payment_method_information(self):
        res = super()._get_payment_method_information()
        res['bank_transfers'] = {
            'mode': 'multi',
            'domain': [('type', '=', 'bank')],
        }
        return res


class AccountPaymentMethodLine(models.Model):
    _inherit = 'account.payment.method.line'

    number = fields.Integer('Number')
    type = fields.Selection(
        selection=[('common', 'Common'), ('deferred', 'Deferred')],
        string='Type',
        default='common',
        required=True,
    )
    format = fields.Selection(
        selection=[
            ('physical', 'Physical'),
            ('virtual', 'Virtual'),
            ('echeq', 'Echeq'),
        ],
        string='Format',
    )
    bank_account_id = fields.Many2one(
        comodel_name='res.partner.bank',
        related='journal_id.bank_account_id',
        string='Bank Account',
    )
    bank_id = fields.Many2one(
        comodel_name='res.bank', related='journal_id.bank_id', string='Bank'
    )
    account_check_id = fields.Many2one(
        comodel_name='account.account',
        string='Check Account',
        help="Account used for account moves with checks. If not set, "
        "account in treasury configuration is used.",
    )
    draft_issued_check_ids = fields.One2many(
        comodel_name='account.check',
        inverse_name='checkbook_id',
        string='Available Checks',
        domain=[
            ('internal_type', '=', 'issued'),
            ('issued_check_state', '=', 'draft'),
        ],
    )
    cancelled_issued_check_ids = fields.One2many(
        comodel_name='account.check',
        inverse_name='checkbook_id',
        string='Cancelled Checks',
        domain=[
            ('internal_type', '=', 'issued'),
            ('issued_check_state', '=', 'cancelled'),
        ],
    )
    issued_check_ids = fields.One2many(
        comodel_name='account.check',
        inverse_name='checkbook_id',
        string='Issued Checks',
        domain=[
            ('internal_type', '=', 'issued'),
            ('issued_check_state', 'not in', ('draft', 'cancelled')),
        ],
    )

    _sql_constraints = [
        (
            "unique_checkbook",
            "unique(journal_id, format, number)",
            _("This checkbook already exists for this journal"),
        ),
    ]
