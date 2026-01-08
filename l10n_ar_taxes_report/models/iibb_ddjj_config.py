from odoo import api, fields, models
from odoo.exceptions import UserError


class IIBBDDJJConfigLine(models.Model):
    _name = "iibb.ddjj.config.jurisdiction.line"
    _description = "IIBB DDJJ Report Jurisdiction Line"

    account_id = fields.Many2one(
        'account.account',
        string="Account",
        required=True,
    )
    coefficient = fields.Float(string="Coefficient", required=True)
    config_id = fields.Many2one(
        comodel_name="iibb.ddjj.config",
        string="Configuration",
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        'res.company',
        string="Company",
        related='config_id.company_id',
        store=True,
        readonly=True,
    )
    percentage = fields.Float(string="Percentage", required=True)
    state_id = fields.Many2one(
        'res.country.state',
        string="State",
        required=True,
        domain="[('country_id.code', '=', 'AR')]",
    )


class IIBBDDJJConfig(models.Model):
    _name = "iibb.ddjj.config"
    _description = "IIBB DDJJ Report Configuration"

    company_id = fields.Many2one('res.company', string="Company")
    jurisdiction_line_ids = fields.One2many(
        comodel_name="iibb.ddjj.config.jurisdiction.line",
        inverse_name="config_id",
        string="Jurisdiction Lines",
    )
    name = fields.Char(string="Configuration Name", required=True)
    total_coeficient = fields.Float(string="Total Coefficient", compute='_compute_total_coefficient', store=True)

    @api.constrains('total_coeficient')
    def _check_total_coefficient(self):
        for record in self:
            if record.total_coeficient > 1.0:
                raise UserError("The total coefficient of all jurisdictions cannot exceed 1.")

    @api.depends('jurisdiction_line_ids.coefficient')
    def _compute_total_coefficient(self):
        for record in self:
            record.total_coeficient = sum(line.coefficient for line in record.jurisdiction_line_ids)
