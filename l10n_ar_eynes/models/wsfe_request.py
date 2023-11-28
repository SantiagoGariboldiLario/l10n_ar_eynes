##############################################################################
#   Copyright (c) 2018 Eynes/E-MIPS (www.eynes.com.ar)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
##############################################################################

from odoo import api, fields, models


class WsRequest(models.Model):
    _name = "ws.request"
    _description = "WS Request"
    _order = "date_request desc"

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

    @api.depends('detail_ids')
    def _compute_nregs(self):
        for rec in self:
            rec.nregs = len(rec.detail_ids)


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
    pos_ar = fields.Char(string='POS', readonly=True, size=16)
    voucher_type = fields.Char(string='Voucher Type', readonly=True, size=64)
    doctype = fields.Integer('Document Type', readonly=True)
    docnum = fields.Char('Document Number', size=32, readonly=True)
    voucher_number = fields.Integer('Voucher Number', readonly=True)
    voucher_date = fields.Date('Voucher Date', readonly=True)
    amount_total = fields.Char('Amount Total', size=64, readonly=True)

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
