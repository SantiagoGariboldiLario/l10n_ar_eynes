from odoo import models, fields


class ResDocumentType(models.Model):
    _name = "res.document.type"
    _description = 'Document type'

    name = fields.Char(string="Name", required=True)
    afip_code = fields.Char(string="AFIP Code", size=2, required=True)
    verification_required = fields.Boolean(string='Verification required', required=True, default=False)
    check_duplicated = fields.Boolean(string="Check Duplicated", required=True, default=False)
    dst_cuit = fields.Boolean(string="Enable DST CUIT", required=True, default=False)
