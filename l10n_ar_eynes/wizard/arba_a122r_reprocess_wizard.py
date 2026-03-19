import json

from odoo import api, fields, models


class ArbaA122rReprocessWizard(models.TransientModel):
    _name = 'arba.a122r.reprocess.wizard'
    _description = 'Asistente de reproceso ARBA A122R'

    company_id = fields.Many2one(
        'res.company', required=True, string='Compañía'
    )
    company_id_domain = fields.Char(
        default=lambda self: self._default_company_ids()
    )
    date_from = fields.Date(required=True, string='Fecha desde')
    date_to = fields.Date(required=True, string='Fecha hasta')
    include_observed = fields.Boolean(
        default=False, string='Incluir observadas'
    )

    @api.model
    def _default_company_ids(self):
        return json.dumps(
            [('id', 'in', self.env.context.get('allowed_company_ids', []))]
        )

    def action_reprocess(self):
        self.ensure_one()
        states = ['pending', 'error']
        if self.include_observed:
            states.append('observed')
        domain = [
            ('company_id', '=', self.company_id.id),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('arba_sync_state', 'in', states),
        ]
        lines = self.env['account.payment.order.retention.line'].search(domain)
        lines = lines.filtered(lambda line: line._is_arba_retention_syncable())
        lines.action_arba_send(raise_on_error=False)
        return {'type': 'ir.actions.act_window_close'}
