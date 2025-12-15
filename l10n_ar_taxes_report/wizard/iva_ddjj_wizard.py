from odoo import fields, models


class IVADDJJ(models.TransientModel):
    _name = "iva.ddjj"
    _description = "IVA DDJJ Report"

    company_id = fields.Many2one('res.company', string="Company", required=True)
    config_id = fields.Many2one(
        'iva.ddjj.config', string="Configuration", required=True
    )
    period = fields.Date(string="Period", required=True)

    def create_pdf(self):
        self.ensure_one()
        # return self.env.ref('l10n_ar_taxes_report.action_report_iva_ddjj').report_action(self)
        return True
