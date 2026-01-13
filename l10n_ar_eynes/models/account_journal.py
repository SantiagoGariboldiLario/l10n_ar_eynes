import logging
import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class AccountJournal(models.Model):
    _name = "account.journal"
    _description = "Journal"
    _inherit = "account.journal"

    def get_default_warehouse(self):
        return self.env['stock.warehouse'].browse(1).id

    @api.onchange('type')
    def _get_tax_id_domain(self):
        domain = [('active', '=', True)]

        if self.type == 'retentions':
            domain.append(
                (
                    'tax_group_id.name',
                    'in',
                    ('Retentions', 'Retenciones'),
                )
            )
        elif self.type == 'perceptions':
            domain.append(
                (
                    'tax_group_id.name',
                    'in',
                    ('Perceptions', 'Percepciones'),
                )
            )

        return {'domain': {'tax_id': domain}}

    afip_code = fields.Char(
        string='AFIP retention code',
        size=6,
        default='',
    )
    code = fields.Char(
        string='POS code',
        size=6,
        required=True,
        help="Point of sale reference code",
        default='',
    )
    denomination = fields.Selection(
        selection=[
            ("a", "A"),
            ("b", "B"),
            ("c", "C"),
            ("e", "E"),
            ('m', 'M'),
            ('oc', 'OC'),
            ('ana', 'ANA'),
            ("not_defined", "Not Defined"),
        ],
        string='Denomination',
        default='not_defined',
    )
    fiscal_position_id = fields.Many2one(
        comodel_name='account.fiscal.position', string='Fiscal Position'
    )
    fiscal_position_ids = fields.Many2many(
        comodel_name='account.fiscal.position',
        relation='journal_fiscal_position_rel',
        column1='journal_id',
        column2='fiscal_position_id',
        string='Fiscal Positions',
    )
    fiscal_type = fields.Selection(
        selection=[
            ('internal', 'Internal Invoice'),
            ('electronic', 'Electronic Invoice'),
        ],
        store=True,
        default='internal',
        help="""
        'internal' (Default): Invoices that doesn't need to be informed to AFIP.
        'electronic': Invoices that will be send and authorized by AFIP (RECE point of sale). To allow this
        feature you must link this journal on WSFE configuration (POS Table)
        """,
    )
    image = fields.Binary("Image", attachment=True)
    image_filename = fields.Char()
    activity_start_date = fields.Date(
        string="Activity Start Date", default=fields.Date.today()
    )
    warehouse_id = fields.Many2one(
        comodel_name='stock.warehouse',
        string='Warehouse',
        default=get_default_warehouse,
    )
    due_date = fields.Date(
        string='Due Date',
        help="Before this date, account moves changes are not allowed. For example: if you want to close "
        "this journal at 31/12/2023 set this field to 01/01/2024. In this way, you can make and modify "
        "entries from 01/01/2024.",
    )
    type = fields.Selection(
        selection_add=[
            ('receipt', 'Receipt'),
            ('payment', 'Payment'),
            ('third_party_checks', 'Third party checks'),
            ('rejected_issued_checks', 'Rejected issued checks'),
            ('retentions', 'Retentions'),
            ('perceptions', 'Perceptions'),
        ],
        ondelete={
            'receipt': lambda recs: recs.write({'type': 'general'}),
            'payment': lambda recs: recs.write({'type': 'general'}),
            'third_party_checks': lambda recs: recs.write({'type': 'general'}),
            'rejected_issued_checks': lambda recs: recs.write(
                {'type': 'general'}
            ),
            'retentions': lambda recs: recs.write({'type': 'general'}),
            'perceptions': lambda recs: recs.write({'type': 'general'}),
        },
        default=False,
    )
    fcred_is_fce_emitter = fields.Boolean(string='FCE Emitter?', default=False)
    suspense_account_id = fields.Many2one(
        comodel_name='account.account',
        check_company=True,
        ondelete='restrict',
        readonly=False,
        store=True,
        compute='_compute_suspense_account_id',
        help="Bank statements transactions will be posted on the suspense account until the final reconciliation "
        "allowing finding the right account.",
        string='Suspense Account',
        domain=lambda self: "[('company_ids', 'parent_of', [company_id]), \
                             ('account_type', 'not in', ('asset_receivable', 'liability_payable'))]",
    )

    # RETENTIONS AND PERCEPTIONS FIELDS
    tax_id = fields.Many2one(
        comodel_name='account.tax',
        string='Tax',
    )
    type_tax_use = fields.Selection(
        string='Tax Application',
        related='tax_id.type_tax_use',
        readonly=True,
    )
    state_id = fields.Many2one(related='tax_id.state_id')
    priority = fields.Integer()
    sequence_id = fields.Many2one(
        comodel_name='ir.sequence',
        string='Sequence',
        copy=False,
        help='This field contains the information related to the numbering '
        'of the journal entries of this journal.',
    )
    sequence_number_next = fields.Integer(
        string='Next Number',
        help='The next sequence number will be used for the next invoice.',
        compute='_compute_seq_number_next',
        inverse='_inverse_seq_number_next',
    )
    cn_sequence_id = fields.Many2one(
        comodel_name='ir.sequence',
        string='Credit Note Sequence',
        copy=False,
        help='This field contains the information related to the numbering '
        'of the journal entries of this journal.',
    )
    cn_sequence_number_next = fields.Integer(
        string='Credit Note Next Number',
        help='The next sequence number will be used for the next invoice.',
        compute='_compute_cn_seq_number_next',
        inverse='_inverse_cn_seq_number_next',
    )
    dn_sequence_id = fields.Many2one(
        comodel_name='ir.sequence',
        string='Debit Note Sequence',
        copy=False,
        help='This field contains the information related to the numbering '
        'of the journal entries of this journal.',
    )
    dn_sequence_number_next = fields.Integer(
        string='Debit Note Next Number',
        help='The next sequence number will be used for the next invoice.',
        compute='_compute_dn_seq_number_next',
        inverse='_inverse_dn_seq_number_next',
    )
    fce_sequence_id = fields.Many2one(
        comodel_name='ir.sequence',
        string='Sequence',
        copy=False,
        help='This field contains the information related to the numbering '
        'of the journal entries of this journal.',
    )
    fce_sequence_number_next = fields.Integer(
        string='Next Number',
        help='The next sequence number will be used for the next invoice.',
        compute='_compute_fce_seq_number_next',
        inverse='_inverse_fce_seq_number_next',
    )
    nce_sequence_id = fields.Many2one(
        comodel_name='ir.sequence',
        string='Credit Note Sequence',
        copy=False,
        help='This field contains the information related to the numbering '
        'of the journal entries of this journal.',
    )
    nce_sequence_number_next = fields.Integer(
        string='Credit Note Next Number',
        help='The next sequence number will be used for the next invoice.',
        compute='_compute_nce_seq_number_next',
        inverse='_inverse_nce_seq_number_next',
    )
    nde_sequence_id = fields.Many2one(
        comodel_name='ir.sequence',
        string='Debit Note Sequence',
        copy=False,
        help='This field contains the information related to the numbering '
        'of the journal entries of this journal.',
    )
    nde_sequence_number_next = fields.Integer(
        string='Debit Note Next Number',
        help='The next sequence number will be used for the next invoice.',
        compute='_compute_nde_seq_number_next',
        inverse='_inverse_nde_seq_number_next',
    )

    @api.constrains('denomination')
    def _check_denomination_not_m(self):
        for record in self:
            if record.denomination == 'm':
                raise ValidationError(
                    _("M denomination is not allowed since December 1° 2025.")
                )

    @api.depends('type')
    def _compute_default_account_type(self):
        super(AccountJournal, self)._compute_default_account_type()
        default_account_id_types = {
            'receipt': 'income%',
            'payment': 'expense%',
        }

        for journal in self.filtered(
            lambda j: j.type in ('payment', 'receipt')
        ):
            if journal.type in default_account_id_types:
                journal.default_account_type = default_account_id_types.get(
                    journal.type, '%'
                )
            else:
                journal.default_account_type = False
        return

    @api.depends('sequence_id.use_date_range', 'sequence_id.number_next_actual')
    def _compute_seq_number_next(self):
        '''Compute 'sequence_number_next' according to the current sequence in use,
        an ir.sequence or an ir.sequence.date_range.
        '''
        for journal in self:
            if journal.sequence_id:
                sequence = journal.sequence_id._get_current_sequence()
                journal.sequence_number_next = sequence.number_next_actual
            else:
                journal.sequence_number_next = 1

    def _inverse_seq_number_next(self):
        '''Inverse 'sequence_number_next' to edit the current sequence next number.'''
        for journal in self:
            if journal.sequence_id and journal.sequence_number_next:
                sequence = journal.sequence_id._get_current_sequence()
                sequence.sudo().number_next = journal.sequence_number_next

    @api.depends(
        'cn_sequence_id.use_date_range', 'cn_sequence_id.number_next_actual'
    )
    def _compute_cn_seq_number_next(self):
        '''Compute 'sequence_number_next' according to the current sequence in use,
        an ir.sequence or an ir.sequence.date_range.
        '''
        for journal in self:
            if journal.cn_sequence_id:
                sequence = journal.cn_sequence_id._get_current_sequence()
                journal.cn_sequence_number_next = sequence.number_next_actual
            else:
                journal.cn_sequence_number_next = 1

    def _inverse_cn_seq_number_next(self):
        '''Inverse 'sequence_number_next' to edit the current sequence next number.'''
        for journal in self:
            if journal.cn_sequence_id and journal.cn_sequence_number_next:
                sequence = journal.cn_sequence_id._get_current_sequence()
                sequence.sudo().number_next = journal.cn_sequence_number_next

    @api.depends(
        'dn_sequence_id.use_date_range', 'dn_sequence_id.number_next_actual'
    )
    def _compute_dn_seq_number_next(self):
        '''Compute 'sequence_number_next' according to the current sequence in use,
        an ir.sequence or an ir.sequence.date_range.
        '''
        for journal in self:
            if journal.dn_sequence_id:
                sequence = journal.dn_sequence_id._get_current_sequence()
                journal.dn_sequence_number_next = sequence.number_next_actual
            else:
                journal.dn_sequence_number_next = 1

    def _inverse_dn_seq_number_next(self):
        '''Inverse 'sequence_number_next' to edit the current sequence next number.'''
        for journal in self:
            if journal.dn_sequence_id and journal.dn_sequence_number_next:
                sequence = journal.dn_sequence_id._get_current_sequence()
                sequence.sudo().number_next = journal.dn_sequence_number_next

    @api.depends(
        'fce_sequence_id.use_date_range', 'fce_sequence_id.number_next_actual'
    )
    def _compute_fce_seq_number_next(self):
        '''Compute 'sequence_number_next' according to the current sequence in use,
        an ir.sequence or an ir.sequence.date_range.
        '''
        for journal in self:
            if journal.fce_sequence_id:
                sequence = journal.fce_sequence_id._get_current_sequence()
                journal.fce_sequence_number_next = sequence.number_next_actual
            else:
                journal.fce_sequence_number_next = 1

    def _inverse_fce_seq_number_next(self):
        '''Inverse 'sequence_number_next' to edit the current sequence next number.'''
        for journal in self:
            if journal.fce_sequence_id and journal.sequence_number_next:
                sequence = journal.fce_sequence_id._get_current_sequence()
                sequence.sudo().number_next = journal.fce_sequence_number_next

    @api.depends(
        'nce_sequence_id.use_date_range', 'nce_sequence_id.number_next_actual'
    )
    def _compute_nce_seq_number_next(self):
        '''Compute 'sequence_number_next' according to the current sequence in use,
        an ir.sequence or an ir.sequence.date_range.
        '''
        for journal in self:
            if journal.nce_sequence_id:
                sequence = journal.nce_sequence_id._get_current_sequence()
                journal.nce_sequence_number_next = sequence.number_next_actual
            else:
                journal.nce_sequence_number_next = 1

    def _inverse_nce_seq_number_next(self):
        '''Inverse 'sequence_number_next' to edit the current sequence next number.'''
        for journal in self:
            if journal.nce_sequence_id and journal.nce_sequence_number_next:
                sequence = journal.nce_sequence_id._get_current_sequence()
                sequence.sudo().number_next = journal.nce_sequence_number_next

    @api.depends(
        'nde_sequence_id.use_date_range', 'nde_sequence_id.number_next_actual'
    )
    def _compute_nde_seq_number_next(self):
        '''Compute 'sequence_number_next' according to the current sequence in use,
        an ir.sequence or an ir.sequence.date_range.
        '''
        for journal in self:
            if journal.nde_sequence_id:
                sequence = journal.nde_sequence_id._get_current_sequence()
                journal.nde_sequence_number_next = sequence.number_next_actual
            else:
                journal.nde_sequence_number_next = 1

    def _inverse_nde_seq_number_next(self):
        '''Inverse 'sequence_number_next' to edit the current sequence next number.'''
        for journal in self:
            if journal.nde_sequence_id and journal.nde_sequence_number_next:
                sequence = journal.nde_sequence_id._get_current_sequence()
                sequence.sudo().number_next = journal.nde_sequence_number_next

    @api.constrains('fcred_is_fce_emitter', 'warehouse_id')
    def _check_no_more_than_one_pos_fce_per_company(self):
        for journal in self:
            if journal.fcred_is_fce_emitter:
                pos = self.env['account.journal'].search_count(
                    [
                        ('warehouse_id', '=', journal.warehouse_id.id),
                        ('fcred_is_fce_emitter', '=', True),
                    ]
                )
                if pos > 1:
                    raise ValidationError(
                        _(
                            "You are not allowed to have more than "
                            "one PoS per shop with FCE Enabled."
                        )
                    )

    def get_pos_number(self):
        num = re.sub("[^0-9]", "", self.code)
        if not num:
            num = 0
        return int(num)

    @api.model
    def create(self, vals):
        journals = super().create(vals)
        for journal in journals:
            if journal.type in (
                'sale',
                'receipt',
                'payment',
                'retentions',
                'perceptions',
            ):
                sequence_vals = journal.create_pos_sequence()
                journal.write(sequence_vals)
        return journals

    def _default_outbound_payment_methods(self):
        res = super()._default_outbound_payment_methods()
        res -= self.env.ref('l10n_ar_eynes.account_payment_method_check')
        return res

    def create_pos_sequence(self):
        "creates a sequence using POS. returns sequence id"
        sequence_vals = {
            'sequence_id': {
                'name': self.name,
                'number_next_actual': self.sequence_number_next,
                'implementation': 'no_gap',
                'padding': 8 if self.type == 'sale' else 0,
                'prefix': '%s-' % self.get_pos_number()
                if self.type == 'sale'
                else '',
            },
        }
        if self.type == 'sale':
            sequence_vals.update(
                {
                    'cn_sequence_id': {
                        'name': self.name + _(' CN'),
                        'number_next_actual': self.cn_sequence_number_next,
                    },
                    'dn_sequence_id': {
                        'name': self.name + _(' DN'),
                        'number_next_actual': self.dn_sequence_number_next,
                    },
                }
            )

        journal_seq_vals = {}
        for seq, vals in sequence_vals.items():
            sequence = self.env['ir.sequence'].create(
                {
                    'name': vals['name'],
                    'implementation': 'no_gap',
                    'active': True,
                    'prefix': vals.get('prefix', '%s-' % self.get_pos_number()),
                    'padding': vals.get('padding', 8),
                    'number_next_actual': vals['number_next_actual'],
                }
            )
            journal_seq_vals.update({seq: sequence.id})
        return journal_seq_vals

    def unlink(self):
        self.sequence_id.unlink()
        self.cn_sequence_id.unlink()
        self.dn_sequence_id.unlink()
        return super().unlink()

    def get_sequence_from_invoice(self, invoice):
        "return the sequence needed depending on the invoice type"
        if invoice.move_type == 'out_refund':
            if invoice.is_FCE_invoice:
                return self.nce_sequence_id
            return self.cn_sequence_id
        elif invoice.move_type == 'out_invoice':
            if invoice.debit_origin_id or invoice.is_debit_note:
                if invoice.is_FCE_invoice:
                    return self.nde_sequence_id
                return self.dn_sequence_id
            if invoice.is_FCE_invoice:
                return self.fce_sequence_id
            return self.sequence_id

    def _get_journal_dashboard_data_batched(self):
        """Ensure custom journal types also provide drag/drop settings to the dashboard."""
        dashboard_data = super()._get_journal_dashboard_data_batched()
        fallback_drag_drop = {
            'image': '/web/static/img/folder.svg',
            'text': _('Drop to create journal entries.'),
        }
        for journal in self:
            journal_data = dashboard_data.get(journal.id)
            if journal_data is not None and 'drag_drop_settings' not in journal_data:
                journal_data['drag_drop_settings'] = fallback_drag_drop
        return dashboard_data
