from odoo import models, fields, api
from odoo.exceptions import ValidationError


class UpdateJournalPeriodWizard(models.TransientModel):
    _name = 'update.journal.period.wizard'
    _description = 'Update Journal Period Wizard'

    def get_all_journals(self):
        journals = self.env['account.journal'].search([])
        journal_ids = []
        for journal in journals:
            rec = self.journal_ids.create({
                'journal_id' : journal.id,
                'wizard_id' : self.id
            })
            journal_ids.append(rec.id)
        return journal_ids

    due_date = fields.Date(
        string='Due Date',
        required=True,
        help="This date is used to restrict new invoices past this date"
    )
    selection_type = fields.Selection(
        selection=[("all", "All Journals"), ("some", "Some Journals")],
        required=True,
        default='all'
    )
    journal_ids = fields.One2many(
        comodel_name='update.journal.period.wizard.line',
        inverse_name='wizard_id',
        string='Journals',
        default=get_all_journals
    )

    def update_periods(self):
        if self.selection_type == 'all':
            journals = self.env['account.journal'].search([])
        else:
            selected_journals = [line.journal_id.id for line in self.journal_ids if line.selected is True]
            if not selected_journals:
                raise ValidationError("no journals selected")
            journals = self.env['account.journal'].browse(selected_journals)

        journals.write({'due_date' : self.due_date})

    @api.constrains('due_date')
    def check_date(self):
        if self.due_date > fields.Date.today():
            raise ValidationError("invalid date")


class UpdateJournalPeriodWizardLine(models.TransientModel):
    _name = 'update.journal.period.wizard.line'
    _description = 'Update Journal Period Wizard Line'

    wizard_id = fields.Many2one(comodel_name='update.journal.period.wizard')
    journal_id = fields.Many2one(string='Journal', comodel_name='account.journal')
    selected = fields.Boolean(string='Selected', default=False)
