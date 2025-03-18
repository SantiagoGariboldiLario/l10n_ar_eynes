from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    apportionable_vat = fields.Boolean(
        related='company_id.apportionable_vat',
        config_parameter='l10n_ar_eynes.apportionable_vat',
        readonly=False,
        default=False,
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
    cot_user = fields.Char(
        related='company_id.cot_user',
        string="COT User (NIF)",
        readonly=False,
    )
    group_check_cot = fields.Boolean(
        related='company_id.group_check_cot',
        string="Enable Web Service",
        readonly=False,
        implied_group="l10n_ar_eynes.group_check_cot",
    )
    special_partner_required_fields = fields.Boolean(
        string="Required Document Type, NIF, and Fiscal Position on partners",
        config_parameter='l10n_ar_eynes.special_partner_required_fields',
        readonly=False,
    )
