import json
import logging

from odoo import _, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    def get_journal_from_pos(self, partner, fiscal_type, pos_config):
        partner_fiscal_position = partner.property_account_position_id
        if fiscal_type == 'internal':
            journals = pos_config.invoice_manual_journal_ids.filtered(
                lambda x: partner_fiscal_position in x.fiscal_position_ids
            )
        else:
            pos_line = self.env['ws.pos.line'].search(
                [
                    ('journal_id', 'in', pos_config.invoice_journal_ids.ids),
                    (
                        'journal_id.fiscal_position_ids',
                        'in',
                        partner_fiscal_position.ids,
                    ),
                ],
                limit=1,
            )
            journals = pos_line.journal_id
        if not journals:
            desc_fiscal_type = (
                _('Internal') if fiscal_type == 'internal' else _('Electronic')
            )
            raise ValidationError(
                _(
                    "No journal of %(fiscal_type)s type was found for "
                    "fiscal position %(fiscal_position)s configured in pos",
                    fiscal_type=desc_fiscal_type,
                    fiscal_position=partner_fiscal_position.display_name,
                )
            )
        return journals[0]

    def is_out_invoice_fce(self, partner, amount_total):
        if self.env.user.company_id.fcred_is_fce_emitter:
            ABC = self.env['afip.big.company'].sudo()
            is_bc = ABC.search([('cuit', '=like', partner.vat)])
            fcred_minimum_amount = self.env.user.company_id.fcred_minimum_amount
            if is_bc and amount_total > fcred_minimum_amount:
                return True
        return False

    def get_pretty_sequence(
        self, journal=False, sequence=False, move_type=False, **kwargs
    ):
        journal = journal or self.journal_id
        sequence = sequence or self.internal_number
        move_type = move_type or self.move_type
        move_type = 'F' if move_type == 'out_invoice' else 'NC'
        denomination = journal.get_pretty_denomination()
        return "%s %s%s" % (move_type, denomination or '', sequence)

    def get_next_sequence_from_pos(
        self,
        partner_id,
        pos_config_id,
        fiscal_type,
        move_type,
        amount_total,
    ):
        partner = self.env['res.partner'].browse(partner_id)
        pos_config = self.env['pos.config'].browse(pos_config_id)
        journal = self.get_journal_from_pos(partner, fiscal_type, pos_config)
        if fiscal_type == 'electronic':
            is_FCE_invoice = self.is_out_invoice_fce(partner, amount_total)
            sequence = self.env['account.move'].get_highest_pos_sequence(
                journal,
                move_type,
                is_fce=is_FCE_invoice,
            )
            pos_number = str(int(journal.get_pos_number())).zfill(5)
            next_seq = '%s-%s' % (pos_number, sequence)
        else:
            if not journal.sequence_id:
                raise ValidationError(
                    _("There is no sequence configured for journal %s")
                    % journal.display_name
                )
            next_seq = journal.sequence_id.get_next_char(
                journal.sequence_id.number_next,
            )
        pretty_sequence = self.get_pretty_sequence(
            journal=journal,
            move_type=move_type,
            sequence=next_seq,
        )
        return {
            'next_seq': next_seq,
            'journal_id': journal.id,
            'full_sequence': pretty_sequence,
        }

    def select_default_voucher_type(self):
        self._compute_voucher_type()
        self.voucher_type_id = self.env['res.voucher.type'].search(
            json.loads(self.voucher_type_domain)
        )[0]
