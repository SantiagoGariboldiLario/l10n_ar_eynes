from odoo import models
from odoo.addons.account.models.chart_template import template


class AccountChartTemplate(models.AbstractModel):
    _inherit = "account.chart.template"

    @template(model='account.journal')
    def _get_account_journal(self, template_code):
        if template_code == 'ar_eynes':
            return self._parse_csv(template_code, 'account.journal')
        vals = super(AccountChartTemplate, self)._get_account_journal(
            template_code
        )
        return vals

    def _select_chart_template(self, country=None):
        super(AccountChartTemplate, self)._select_chart_template(country)
        return [('ar_eynes', '🇦🇷 Argentina - Eynes')]

    def _get_chart_template_mapping(self, get_all=False):
        mapping = super(AccountChartTemplate, self)._get_chart_template_mapping(
            get_all=get_all
        )
        mapping['ar_eynes'] = {
            'name': '🇦🇷 Argentina - Eynes',
            'country_id': 10,
            'country_code': 'AR',
            'parent': None,
            'sequence': 1,
            'visible': True,
            'installed': False,
            'module': 'l10n_ar_eynes',
        }
        return mapping

    def _load(self, template_code, company, install_demo):
        template_code = 'ar_eynes'
        return super(AccountChartTemplate, self)._load(
            template_code, company, install_demo
        )

    def _setup_utility_bank_accounts(
        self, template_code, company, template_data
    ):
        if template_code != 'ar_eynes':
            return super(
                AccountChartTemplate, self
            )._setup_utility_bank_accounts(
                template_code, company, template_data
            )
