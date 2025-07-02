from odoo import fields, models


class ResDocumentType(models.Model):
    _name = "res.document.type"
    _description = 'Document type'

    active = fields.Boolean(default=True)
    afip_code = fields.Char(string="AFIP Code", size=2, required=True)
    check_duplicated = fields.Boolean(
        string="Check Duplicated", required=True, default=False
    )
    dst_cuit = fields.Boolean(
        string="Enable DST CUIT", required=True, default=False
    )
    name = fields.Char(string="Name", required=True)
    verification_required = fields.Boolean(
        string='Verification required', required=True, default=False
    )

    def get_website_sale_documents(self, mode='billing'):
        cuit = self.sudo().env.ref('l10n_ar_eynes.document_cuit').name
        cuil = self.sudo().env.ref('l10n_ar_eynes.document_cuil').name
        dni = self.sudo().env.ref('l10n_ar_eynes.document_dni').name
        return self.sudo().search([('name', 'in', (cuit, cuil, dni))])
