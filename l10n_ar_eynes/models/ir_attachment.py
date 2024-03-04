from odoo import fields, models


class IrAttachment(models.Model):

    _inherit = "ir.attachment"

    report_file_id = fields.Many2one('report.files')
