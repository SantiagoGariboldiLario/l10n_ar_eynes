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

    def _get_voucher_type(self, move):
        return self.env['res.voucher.type'].search(
            [
                ('denomination', '=', move.denomination),
                ('doc_type', '=', 'dn'),
                ('afip_code', '>' if move.is_FCE_invoice else '<', 200),
            ],
            limit=1,
        )

    def _prepare_default_values(self, move):
        res = super(AccountDebitNote, self)._prepare_default_values(move)

        # Add perception lines
        perceptions = []
        if self.copy_lines:
            for p in move.perception_ids:
                perceptions.append(
                    (
                        0,
                        0,
                        {
                            'amount': p.amount,
                            'base': p.base,
                            'concept_id': p.concept_id.id,
                            'manual': p.manual,
                            'name': p.name,
                            'partner_id': p.partner_id.id,
                            'perception_id': p.perception_id.id,
                            'reg_code': p.reg_code,
                            'state_id': p.state_id.id,
                            'tax_app_id': p.tax_app_id.id,
                            'vat': p.vat,
                        },
                    )
                )
        res.update(
            {
                'is_debit_note': True,
                'partner_shipping_id': move.partner_shipping_id.id,
                'perception_ids': perceptions,
                'associated_inv_ids': [move.id],
                'currency_id': move.currency_id.id,
                'currency_rate': move.currency_rate,
                'is_multi_currency': move.is_multi_currency,
                'voucher_type_id': self._get_voucher_type(move).id,
            }
        )

        return res
