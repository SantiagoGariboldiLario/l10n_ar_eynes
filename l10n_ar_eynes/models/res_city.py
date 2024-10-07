##############################################################################
#   Copyright (c) 2018 Eynes/E-MIPS (www.eynes.com.ar)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
##############################################################################

from odoo import fields, models


class ResCity(models.Model):
    _inherit = 'res.city'

    afip_code = fields.Char(string='AFIP Code', size=16)
