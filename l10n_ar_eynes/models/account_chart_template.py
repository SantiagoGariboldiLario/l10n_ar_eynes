from odoo import models
from odoo.addons.account.models.chart_template import template


class AccountChartTemplate(models.AbstractModel):
    _inherit = "account.chart.template"

    @template(model='account.journal')
    def _get_account_journal(self, template_code):
        vals = super()._get_account_journal(template_code)
        if template_code == 'generic_coa':
            if 'cash' in vals:
                vals['cash']['code'] = 'CASH'
            if 'bank' in vals:
                vals['bank']['code'] = 'BANK'
        return vals
