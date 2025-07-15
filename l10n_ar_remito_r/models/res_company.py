from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"
    _description = "Res Company Tecnitower"

    autoprinter_num = fields.Char(string="Autoprinter Number")
    autoprinter_code = fields.Char(string="Autoprinter Code")
    autoprinter_due_date = fields.Date(string="Autoprinter Due Date")
    dnrp_num = fields.Char(string="DNRP number", size=100)
