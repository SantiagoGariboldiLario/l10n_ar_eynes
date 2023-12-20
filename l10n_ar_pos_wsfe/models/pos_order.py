import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = 'pos.order'

    invoice_journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Invoice Journal',
        copy=False,
    )
    is_wsfe = fields.Boolean(
        string='Is Electronic Invoice',
        copy=False,
    )

    @api.model
    def _order_fields(self, ui_order):
        res = super(PosOrder, self)._order_fields(ui_order)
        res['invoice_journal_id'] = ui_order['invoice_journal_id']
        res['is_wsfe'] = ui_order['inv_electronic_mode']
        return res

    def _prepare_invoice_vals(self):
        res = super(PosOrder, self)._prepare_invoice_vals()
        if self.invoice_journal_id:
            res['journal_id'] = self.invoice_journal_id.id
        if self.is_wsfe:
            fiscal_position = self.partner_id.property_account_position_id
            if fiscal_position:
                res['fiscal_position_id'] = fiscal_position.id
        return res

    def _apply_invoice_payments(self):
        if (
            self.account_move.ws_request_ids
            and self.account_move.state != 'posted'
        ):
            last_request = self.account_move.ws_request_ids.sorted('id')[-1]
            if not last_request.cae:
                raise UserError(last_request.observations)
        return super(PosOrder, self)._apply_invoice_payments()
