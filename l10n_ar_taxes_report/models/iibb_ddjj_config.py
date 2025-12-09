from odoo import fields, models


class IIBBDDJJConfigLine(models.Model):
    _name = "iibb.ddjj.config.jurisdiction.line"
    _description = "IIBB DDJJ Report Jurisdiction Line"

    account_id = fields.Many2one(
        'account.account',
        string="Account",
        required=True,
        company_dependent=True,
    )
    config_id = fields.Many2one(
        comodel_name="iibb.ddjj.config",
        string="Configuration",
        required=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        'res.country',
        string="Company",
        related='config_id.company_id',
        store=True,
        readonly=True,
    )
    name = fields.Char(string="Jurisdiction Name", required=True)
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
