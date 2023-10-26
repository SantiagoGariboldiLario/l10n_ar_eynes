from odoo import api, fields, models


class SicoreFiscalPosition(models.Model):
    _name = 'sicore.fiscal.position'

    code = fields.Char('Code', required=True)
    config_id = fields.Many2one('sicore.config')
    fiscal_position = fields.Many2one('account.fiscal.position', required=True)


class SicoreConfig(models.Model):
    _name = 'sicore.config'
    _rec_name = 'name'

    fiscal_position_ids = fields.One2many(
        'sicore.fiscal.position', 'config_id', string='Fiscal Positions'
    )
    name = fields.Char('Name', required=True)


class SicoreGeneratedFiles(models.Model):
    _name = 'sicore.generated.files'

    attachment_id = fields.Many2one('ir.attachment')
    code = fields.Char()
    datas = fields.Binary(related='attachment_id.datas')
    name = fields.Char(compute='_compute_name')
    period_start = fields.Date('Date start')
    period_end = fields.Date('Date end')
    presentation_date = fields.Date(
        'Date of presentation', default=fields.Date.today()
    )

    @api.depends('code')
    def _compute_name(self):
        for rec in self:
            rec.name = rec.code
