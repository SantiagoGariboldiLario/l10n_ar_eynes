##############################################################################
#   Copyright (c) 2018 Eynes/E-MIPS (www.eynes.com.ar)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
##############################################################################

from odoo import fields, models


class AccountMoveOptional(models.Model):
    _name = "account.move.optional"
    _description = 'Invoice Optional Line'

    code = fields.Char(related='optional_id.code')
    invoice_id = fields.Many2one('account.move', 'Invoice')
    optional_id = fields.Many2one('ws.optionals', 'Optional')
    value = fields.Char('Value', size=255)
