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
        # Not active_model: after the document layout wizard the context
        # points to base.document.layout
        model = 'account.tax.subjournal.apportionable.wizard'
        docs = self.env[model].browse(
            docids or self.env.context.get('active_ids')
        )

        return {
            'doc_ids': self.ids,
            'doc_model': model,
            'data': data,
            'docs': docs,
        }
