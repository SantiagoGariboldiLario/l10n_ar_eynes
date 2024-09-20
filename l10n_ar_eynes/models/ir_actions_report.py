from odoo import _, models
from odoo.exceptions import UserError


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _is_retention_certificate_report(self, report_ref):
        return (
            self._get_report(report_ref).report_name
            == 'l10n_ar_eynes.retention_certificate_qweb'
        )

    def _render_qweb_pdf(self, report_ref, res_ids=None, data=None):
        orders = self.env['account.payment.order'].browse(res_ids)
        if self._is_retention_certificate_report(report_ref):
            if any(x.is_receipt() for x in orders):
                raise UserError(_("Only Payment Orders could be printed."))

        return super()._render_qweb_pdf(report_ref, res_ids=res_ids, data=data)
