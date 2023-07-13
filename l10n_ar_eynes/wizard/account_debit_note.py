from odoo import fields, models


class AccountDebitNote(models.TransientModel):
    _inherit = 'account.debit.note'

    def default_journal(self):
        invoice_id = self._context.get('active_id')
        return self.env['account.move'].browse(invoice_id).journal_id.id

    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Use Specific Journal',
        help='If empty, uses the journal of the journal entry to be debited.',
        default=default_journal,
    )

    def _prepare_default_values(self, move):
        res = super(AccountDebitNote, self)._prepare_default_values(move)
        res['is_debit_note'] = True

        # Add perception lines
        if self.copy_lines:
            perceptions = []
            for p in move.perception_ids:
                perceptions.append(
                    (
                        0,
                        0,
                        {
                            'amount': p.amount,
                            'base': p.base,
                            'base_amount': p.base_amount,
                            'concept_id': p.concept_id.id,
                            'manual': p.manual,
                            'name': p.name,
                            'partner_id': p.partner_id.id,
                            'perception_id': p.perception_id.id,
                            'reg_code': p.reg_code,
                            'state_id': p.state_id.id,
                            'tax_amount': p.tax_amount,
                            'tax_app_id': p.tax_app_id.id,
                            'vat': p.vat,
                        },
                    )
                )
            res.update(
                {
                    # 'address_shipping_id': move.address_shipping_id.id,
                    'perception_ids': perceptions,
                }
            )

        return res
