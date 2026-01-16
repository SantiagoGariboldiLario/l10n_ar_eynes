from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    apportionable_vat = fields.Boolean(
        related='company_id.apportionable_vat',
        config_parameter='l10n_ar_eynes.apportionable_vat',
        readonly=False,
        default=False,
    )
    case_convertion = fields.Selection(
        selection=[
            ('title', 'Titlecase'),
            ('lower', 'Lowercase'),
            ('upper', 'Uppercase'),
            ('capitalize', 'Capitalize'),
        ],
        help="Converts fetched text to specific case.",
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

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'case_convertion' in fields_list:
            allowed = {
                opt[0] for opt in self._fields['case_convertion'].selection
            }
            param_val = res.get('case_convertion') or self.env[
                'ir.config_parameter'
            ].sudo().get_param('l10n_ar_eynes.case_convertion')
            if param_val not in allowed:
                res['case_convertion'] = 'title'
        return res

    def get_values(self):
        res = super().get_values()
        allowed = {opt[0] for opt in self._fields['case_convertion'].selection}
        param_val = res.get('case_convertion')
        if param_val not in allowed:
            res['case_convertion'] = 'title'
            self.env['ir.config_parameter'].sudo().set_param(
                'l10n_ar_eynes.case_convertion', 'title'
            )
        return res
