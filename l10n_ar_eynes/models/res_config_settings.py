from odoo import fields, models, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    rejected_issued_checks_journal_id = fields.Many2one(
        comodel_name='account.journal',
        related='company_id.rejected_issued_checks_journal_id',
        readonly=False,
        domain="[('company_id', '=', company_id)]",
        string='Rejected issued checks journal',
    )

    def set_values(self):
        super(ResConfigSettings, self).set_values()

    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        return res
