from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class UpdateJournalPeriodWizard(models.TransientModel):
    _name = 'update.journal.period.wizard'
    _description = 'Update Journal Period Wizard'

    due_date = fields.Date(
        string='Due Date',
        required=True,
        help="This date is used to restrict new invoices past this date",
    )
    selection_type = fields.Selection(
        selection=[("all", "All Journals"), ("some", "Some Journals")],
        required=True,
        default=lambda self: self._get_default_type(),
    )
    journal_ids = fields.One2many(
        comodel_name='update.journal.period.wizard.line',
        inverse_name='wizard_id',
        string='Journals',
        default=lambda self: self._get_all_journals(),
    )

    @api.constrains('due_date')
    def _check_date(self):
        if self.due_date > fields.Date.today():
            raise ValidationError(_("invalid date"))

    def update_periods(self):
        if self.selection_type == 'all':
            journals = self.env['account.journal'].search([])
        else:
            selected_journals = [
                line.journal_id.id
                for line in self.journal_ids
                if line.selected is True
            ]
            if not selected_journals:
                raise ValidationError(_("no journals selected"))
            journals = self.env['account.journal'].browse(selected_journals)

        journals.write({'due_date': self.due_date})

    def _get_all_journals(self):
        active_model = self.env.context.get('active_model')
        active_journals = []
        if active_model and active_model == 'account.journal':
            active_journals = self.env.context.get('active_ids', [])
        journals = self.env['account.journal'].search([])
        journal_ids = []
        for journal in journals:
            rec = self.journal_ids.create(
                {
                    'journal_id': journal.id,
                    'wizard_id': self.id,
                    'selected': journal.id in active_journals,
                }
            )
            journal_ids.append(rec.id)
        return journal_ids

    def _get_default_type(self):
        active_model = self.env.context.get('active_model')
        if active_model and active_model == 'account.journal':
            return 'some'
        return 'all'


class UpdateJournalPeriodWizardLine(models.TransientModel):
    _name = 'update.journal.period.wizard.line'
    _description = 'Update Journal Period Wizard Line'

    wizard_id = fields.Many2one(comodel_name='update.journal.period.wizard')
    journal_id = fields.Many2one(
        string='Journal', comodel_name='account.journal'
    )
    selected = fields.Boolean(string='Selected', default=False)
