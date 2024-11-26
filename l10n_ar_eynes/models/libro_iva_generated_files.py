##############################################################################
#
#   Copyright (c) 2022-2023 Eynes SRL  (Eynes - Ingenieria del software)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
#
##############################################################################

from odoo import fields, models


class LibroivaGeneratedFiles(models.Model):
    _name = 'libroiva.generated.files'

    attachment_id = fields.Many2one('ir.attachment')
    code = fields.Char()
    company_id = fields.Many2one('res.company')
    datas = fields.Binary(related='attachment_id.datas')
    date_from = fields.Date(string='Date From')
    date_to = fields.Date(string='Date To')
