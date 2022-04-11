from odoo import fields, models


class AccountJournal(models.Model):
    _name = "account.journal"
    _description = "Journal"
    _inherit = "account.journal"

    def get_default_warehouse(self):
        return self.env['stock.warehouse'].browse(1).id

    code = fields.Char(
        string='POS code',
        size=5,
        required=True,
        help="Point of sale reference code",
        default='')

    denomination = fields.Selection(
        [("a", "A"), ("b", "B"), ("c", "C"), ("e", "E"), ("not_defined", "Not Defined")],
        string='Denomination',
        default='not_defined')

    fiscal_position_id = fields.Many2one(
        comodel_name='account.fiscal.position',
        string='Fiscal Position')

    activity_start_date = fields.Date(
        string="Activity Start Date",
        default=fields.date.today())

    warehouse_id = fields.Many2one(
        comodel_name='stock.warehouse',
        string='Warehouse',
        default=get_default_warehouse)

    due_date = fields.Date(
        string='Due Date',
        help='after this expiration date, account moves are not allowed to use this journal till its extended')

    type = fields.Selection(
        selection_add=[('receipt', 'Receipt'), ('payment', 'Payment')],
        ondelete={
            'receipt': lambda recs: recs.write({'type': 'general'}),
            'payment': lambda recs: recs.write({'type': 'general'})
        }
    )

    _sql_constraints = [
        ('code_unique', 'unique(code)', 'code already exists!')
    ]
