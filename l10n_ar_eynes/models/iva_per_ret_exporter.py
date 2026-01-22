##############################################################################
#
#   Copyright (c) 2022-2023 Eynes SRL  (Eynes - Ingenieria del software)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
#
##############################################################################

from odoo import fields, models


class IVAPerGeneratedFiles(models.Model):
    _name = 'iva.per.generated.files'

    code = fields.Char()
    company_id = fields.Many2one('res.company')
    datas = fields.Binary(related='attachment_id.datas')
    date_from = fields.Date(string='Date From')
    date_to = fields.Date(string='Date To')
    attachment_id = fields.Many2one('ir.attachment')


class IVARetGeneratedFiles(models.Model):
    _name = 'iva.ret.generated.files'
    code = fields.Char()
    company_id = fields.Many2one('res.company')
    datas = fields.Binary(related='attachment_id.datas')
    date_from = fields.Date(string='Date From')
    date_to = fields.Date(string='Date To')
    attachment_id = fields.Many2one('ir.attachment')
