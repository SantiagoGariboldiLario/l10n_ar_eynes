from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # rejected_issued_checks_journal_id = fields.Many2one(
    #     comodel_name='account.journal',
    #     related='company_id.rejected_issued_checks_journal_id',
    #     readonly=False,
    #     domain="[('company_id', '=', company_id)]",
    #     string='Rejected issued checks journal',
    # )
    cot_user = fields.Char(
        related='company_id.cot_user',
        string="COT User (NIF)",
        readonly=False,
    )
    cot_pass = fields.Char(
        related='company_id.cot_pass',
        string="COT Password",
        readonly=False,
    )
    cot_url = fields.Char(
        related='company_id.cot_url',
        string="COT URL",
        readonly=False,
    )
    group_check_cot = fields.Boolean(
        related='company_id.group_check_cot',
        string="Enable Web Service",
        readonly=False,
        implied_group="l10n_ar_eynes.group_check_cot",
    )

    case_convertion = fields.Selection(
        [
            ('title', 'Titlecase'),
            ('lower', 'Lowercase'),
            ('upper', 'Uppercase'),
            ('capitalize', 'Capitalize'),
        ],
        help="Converts fetched text to specific case.",
        required=True,
        default='title',
        config_parameter='l10n_ar_eynes.case_convertion',
    )

    def set_values(self):
        res = super().set_values()
        return res

    @api.model
    def get_values(self):
        res = super().get_values()
        return res
