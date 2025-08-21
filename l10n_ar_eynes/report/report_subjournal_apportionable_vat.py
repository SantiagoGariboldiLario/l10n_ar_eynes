##############################################################################
#
#   Copyright (c) 2025 Eynes SRL  (Eynes - Ingenieria del software)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
#
##############################################################################


from odoo import api, models


class SubjournalApportionableReport(models.AbstractModel):
    _name = 'report.l10n_ar_eynes.subjournal_apportionable_vat_qweb'
    _description = "Account tax subjournal report for apportionable VAT taxes"

    @api.model
    def _get_report_values(self, docids, data=None):
        model = self.env.context.get('active_model')
        docs = self.env[model].browse(self.env.context.get('active_id'))

        return {
            'doc_ids': self.ids,
            'doc_model': model,
            'data': data,
            'docs': docs,
        }
