from odoo import fields, models


class SicoreFiscalPosition(models.Model):
    _name = 'sicore.fiscal.position'

    fiscal_position = fields.Many2one('account.fiscal.position', required=True)
    code = fields.Char('Code', required=True)
    config_id = fields.Many2one('sicore.config')


class SicoreConfig(models.Model):
    _name = 'sicore.config'
    _rec_name = 'name'

    name = fields.Char('Name', required=True)
    fiscal_position_ids = fields.One2many(
        'sicore.fiscal.position', 'config_id', string='Fiscal Positions'
    )


class SicoreGeneratedFiles(models.Model):
    _name = 'sicore.generated.files'

    code = fields.Char()
    period_start = fields.Date('Date start')
    period_end = fields.Date('Date end')
    presentation_date = fields.Date(
        'Date of presentation', default=fields.Date.today()
    )
    attachment_id = fields.Many2one('ir.attachment')
