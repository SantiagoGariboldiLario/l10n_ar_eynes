from odoo import _, fields, models


class ForceJournalChangewizard(models.TransientModel):
    _name = 'force.journal.change.wizard'
    _description = 'Change the journal of a posted entry'

    new_journal_id = fields.Many2one(
        comodel_name='account.journal', required=True
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company.id,
    )

    def force_journal_change(self):
        active_ids = self.env.context.get('active_ids', [])
        if not active_ids:
            return

        moves = self.env['account.move'].browse(active_ids)
        invoices = moves.filtered(
            lambda move: move.is_invoice(include_receipts=True)
        )
        draft_moves = (moves - invoices).filtered(
            lambda move: move.state == 'draft'
        )
        no_draft_moves = moves - invoices - draft_moves
        # next_number = self.new_journal_id.
        for move in draft_moves:
            move.name = '/'
            move.posted_before = False
            move.write(
                {
                    'journal_id': self.new_journal_id.id,
                    'sequence_number': 0,
                }
            )

        message = ''
        if invoices:
            message += _(
                "You can't change the Journal of an invoice: %(inv_names)s\n",
                inv_names=', '.join(
                    invoice.display_name for invoice in invoices
                ),
            )
        if no_draft_moves:
            message += _(
                "Move must be on 'draft' to change the Journal: %(move_names)s\n",
                move_names=', '.join(
                    move.display_name for move in no_draft_moves
                ),
            )
        if len(draft_moves) == 0:
            message += _(
                'There are no moves to change the Journal\n',
            )
        else:
            message += _(
                'Moves that you can change the Journal: %(move_names)s\n',
                move_names=', '.join(move.display_name for move in draft_moves),
            )

        context = dict(self._context or {})
        context['message'] = message
        view = self.env.ref('popup_messages.message_wizard')
        view_id = view and view.id or False

        return {
            'name': _('Force Journal Result'),
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'message.wizard',
            'views': [(view_id, 'form')],
            'view_id': view_id,
            'target': 'new',
            'context': context,
        }
