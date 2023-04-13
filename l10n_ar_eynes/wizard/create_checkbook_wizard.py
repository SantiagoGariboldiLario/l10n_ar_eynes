from odoo import fields, models, _, api
from odoo.exceptions import ValidationError


class CreateCheckbookWizard(models.TransientModel):
    _name = 'create.checkbook.wizard'
    _description = 'Create Checkbook Wizard'
    _rec_name = 'number'

    number = fields.Char(string='Checkbook Number', required=True)
    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Journal',
        required=True,
        domain=[('type', '=', 'bank')]
    )
    checkbook_format = fields.Selection(
        selection=[
            ('physical', 'Physical'),
            ('virtual', 'Virtual'),
            ('echeq', 'Echeq')
        ],
        string='Format',
        required=True
    )
    start_num = fields.Char('Start Number', size=8)
    end_num = fields.Char('End Number', size=8)

    def create_checkbook(self):
        payment_method = self.env.ref(
            'account_check_printing.account_payment_method_check'
        )

        payment_method_name = _(
            'Checkbook %(name)s %(format)s-%(number)s',
            name=self.journal_id.name,
            format=self.checkbook_format[0].upper(),
            number=self.number
        )

        self.journal_id.outbound_payment_method_line_ids = [(0, 0, {
            'journal_id' : self.journal_id.id,
            'payment_method_id' : payment_method.id,
            'name' : payment_method_name,
            'number': self.number,
            'format' : self.checkbook_format
        })]

        if self.checkbook_format != 'echeq':
            self.check_range()

        if self.checkbook_format != 'echeq':
            start_numer = int(self.start_num)
            end_number = int(self.end_num)

            for i in range(start_numer, end_number + 1):
                self.env['account.check'].create({
                    'number': str(i).zfill(8),
                    'journal_id' : self.journal_id.id,
                    'bank_id' : self.journal_id.bank_id.id,
                    'checkbook_id' : self.env['account.payment.method.line'].search([('name', '=', payment_method_name)]).id,
                    'checkbook_format' : self.checkbook_format,
                    'internal_type' : 'issued',
                    'issued_check_state' : 'draft',
                    'type' : 'common',
                })

        return {
            'type': 'ir.actions.client',
            'tag': 'reload'
        }

    @api.onchange('number')
    def _onchange_number(self):
        if not self.number:
            return
        if not self.number.isnumeric():
            raise ValidationError(_('Checkbook Number must be numeric'))

    @api.onchange('start_num')
    def _onchange_start_num(self):
        if not self.start_num:
            return
        if not self.start_num.isnumeric():
            raise ValidationError(_('start number must be an integer'))
        self.start_num = self.start_num.zfill(8)

    @api.onchange('end_num')
    def _onchange_end_num(self):
        if not self.end_num:
            return
        if not self.end_num.isnumeric():
            raise ValidationError(_('End number must be an integer'))
        self.end_num = self.end_num.zfill(8)

    def check_range(self):
        if int(self.start_num) > int(self.end_num):
            raise ValidationError(_("Start number must be smaller than End number"))
