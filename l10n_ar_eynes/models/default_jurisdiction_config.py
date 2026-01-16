##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (c) 2019 E-MIPS (http://www.e-mips.com.ar)
#    Copyright (c) 2019 Eynes (http://www.eynes.com.ar)
#    All Rights Reserved. See AUTHORS for details.
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General
#    Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class DefaultJurisdictionConfiguration(models.Model):
    _name = 'report.default.jurisdiction.configuration'

    pos_ar_id = fields.Many2one(
        comodel_name='account.journal',
        domain="[('type', '=', 'sale')]",
        required=True,
        string="Point of Sale",
    )
    state_id = fields.Many2one(
        comodel_name='res.country.state',
        domain=lambda self: [
            ('country_id', '=', self.env.company.country_id.id)
        ],
        required=True,
        string="State",
    )

    @api.constrains('pos_ar_id', 'state_id')
    def _check_unique(self):
        for rec in self:
            if rec.search_count([('pos_ar_id', '=', rec.pos_ar_id.id)]) > 1:
                raise ValidationError(
                    _(
                        "You can not have more than one default for the "
                        + "same point of sale."
                    )
                )

    display_name = fields.Char(compute='_compute_display_name', store=True)

    @api.depends('pos_ar_id.name', 'state_id.name')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = '%s -> %s' % (
                rec.pos_ar_id.name,
                rec.state_id.name,
            )
