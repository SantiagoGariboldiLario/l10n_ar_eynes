##############################################################################
#
#   Copyright (c) 2022-2023 Eynes SRL  (Eynes - Ingenieria del software)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
#
##############################################################################

from odoo import fields, models


class ArbaGeneratedFiles(models.Model):
    _name = 'arba.generated.files'

    code = fields.Char()
    company_id = fields.Many2one('res.company')
    datas = fields.Binary(related='attachment_id.datas')
    datas_fname = fields.Char(related='attachment_id.name')
    date_from = fields.Date(string='Date From')
    date_to = fields.Date(string='Date To')
    attachment_id = fields.Many2one('ir.attachment')
