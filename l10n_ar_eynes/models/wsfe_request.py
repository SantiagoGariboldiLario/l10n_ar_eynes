##############################################################################
#   Copyright (c) 2018 Eynes/E-MIPS (www.eynes.com.ar)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
##############################################################################

from odoo import api, fields, models


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
