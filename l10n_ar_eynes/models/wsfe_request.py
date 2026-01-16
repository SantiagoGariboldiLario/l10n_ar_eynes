##############################################################################
#   Copyright (c) 2018 Eynes/E-MIPS (www.eynes.com.ar)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
##############################################################################

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class WsRequest(models.Model):
    _name = "ws.request"
    _description = "WS Request"
    _order = "date_request desc"

    name = fields.Char(compute='_compute_name', readonly=True)
    detail_ids = fields.One2many(
        comodel_name='ws.request.detail',
        inverse_name='request_id',
        string='Details',
        readonly=True,
    )
    date_request = fields.Datetime(
        string='Request Date', required=True, readonly=True
    )
    nregs = fields.Integer(string='Number of Records', readonly=True)

    @api.depends('date_request')
    def _compute_name(self):
        for rec in self:
            rec.name = 'Req %s / %s' % (rec.id, rec.date_request)

    @api.model_create_multi
    def create(self, vals):
        # Use naive UTC datetime to match field expectations in v19
        user_tz_date = fields.Datetime.now()
        for val in vals:
            val.update({'date_request': user_tz_date})
        return super().create(vals)

    def unlink(self):
        self.detail_ids.unlink()
        return super().unlink()


class WsRequestDetail(models.Model):
    _name = "ws.request.detail"
    _description = "WS Request Detail"

    request_id = fields.Many2one(
        comodel_name='ws.request',
        string='Request',
    )

    invoice_id = fields.Many2one(
        comodel_name='account.move', string='Voucher', readonly=True
    )
    pos_ar = fields.Integer(string='POS', readonly=True)
    voucher_type = fields.Integer(string='Voucher Type', readonly=True)
    doctype = fields.Char('Document Type', readonly=True)
    docnum = fields.Char('Document Number', size=32, readonly=True)
    voucher_number = fields.Integer('Voucher Number', readonly=True)
    voucher_date = fields.Date('Voucher Date', readonly=True)
    amount_total = fields.Float('Amount Total', size=64, readonly=True)
    currency = fields.Char(readonly=True)
    currency_rate = fields.Char(readonly=True)
    xml_request = fields.Text('XML', readonly=True)
    is_currency_request = fields.Boolean(default=False)
    cae = fields.Char('CAE', readonly=True, size=64)
    cae_due_date = fields.Date('CAE Due Date', readonly=True)
    result = fields.Selection(
        [
            ('A', 'Approved'),
            ('R', 'Rejected'),
            ('P', 'Partial'),
            ('E', 'Error'),
        ],
        'Result',
        readonly=True,
    )
    observations = fields.Text('Observations', readonly=True)
    events = fields.Char('Events', readonly=True)
    errors = fields.Text('Errors', readonly=True)

    @api.ondelete(at_uninstall=False)
    def _check_ws_request_detail_unlink(self):
        user = self.env.user

        if not (
            user.has_group('l10n_ar_eynes.group_arca_request_administrator')
            or any(self.mapped('is_currency_request'))
        ):
            raise ValidationError(
                _('You do not have permission to delete this record.')
            )

        approved_requests = self.filtered(lambda r: r.result == 'A')
        if approved_requests:
            raise ValidationError(
                _('You cannot delete a request with approved status.')
            )

    def unlink(self):
        """
        Unlink request restrictions was moved to api.ondelete method
        """
        WsRequestDetail = self.env['ws.request.detail']

        for rec in self:
            # Si este es el único detail del request y no venimos del padre
            other_details = WsRequestDetail.search(
                [('request_id', '=', rec.request_id.id)]
            )
            if other_details == rec and not self.env.context.get(
                'delete_parent', False
            ):
                rec.request_id.with_context(delete_parent=True).unlink()
            else:
                super(WsRequestDetail, rec).unlink()

        return True
