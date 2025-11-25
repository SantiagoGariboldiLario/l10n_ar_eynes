import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def _reload_chart_template_data(cr):
    env = api.Environment(cr, SUPERUSER_ID, {})
    companies = env['res.company'].search([])
    for company in companies:
        env['res.config.settings'].sudo().search(
            [('company_id', '=', company.id)]
        ).reload_template()
        company.write({})


def migrate(cr, version):
    _logger.info("Reload Chart Template data with new taxes and journals...")
    _reload_chart_template_data(cr)
