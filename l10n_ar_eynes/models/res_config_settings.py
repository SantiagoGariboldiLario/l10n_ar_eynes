from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    rejected_issued_checks_journal_id = fields.Many2one(
        comodel_name='account.journal',
        related='company_id.rejected_issued_checks_journal_id',
        readonly=False,
        domain="[('company_id', '=', company_id)]",
        string='Rejected issued checks journal',
    )
    cot_user = fields.Char(string="COT User (NIF)")
    cot_pass = fields.Char(string="COT Password")
    cot_url = fields.Char(string="COT URL")
    group_check_cot = fields.Boolean(
        string="Enable Web Service",
        implied_group="l10n_ar_delivery_cot.group_check_cot",
    )

    def set_values(self):
        res = super(ResConfigSettings, self).set_values()
        self.env["ir.config_parameter"].sudo().set_params(
            {
                "cot_user": self.cot_user,
                "cot_pass": self.cot_pass,
                "cot_url": self.cot_url,
            }
        )
        return res

    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        params = self.env["ir.config_parameter"].sudo()
        cot_user = params.get_param("cot_user", default="CUIT")
        cot_pass = params.get_param("cot_pass", default="Password")
        cot_url = params.get_param("cot_url", default="http://arba.gov.ar/")
        res.update(
            {
                "cot_user": cot_user,
                "cot_pass": cot_pass,
                "cot_url": cot_url,
            }
        )
        return res
