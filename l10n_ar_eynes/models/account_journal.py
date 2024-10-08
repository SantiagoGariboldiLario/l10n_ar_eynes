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
        string="Activity Start Date", default=fields.date.today()
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
        domain=lambda self: "[('deprecated', '=', False), ('company_id', '=', company_id), \
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
        if self.fcred_is_fce_emitter:
            pos = self.env['account.journal'].search_count(
                [
                    ('warehouse_id', '=', self.warehouse_id.id),
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
        res = super().create(vals)
        if res and res.type in (
            'sale',
            'receipt',
            'payment',
            'retentions',
            'perceptions',
        ):
            sequence_vals = res.create_pos_sequence()
            res.write(sequence_vals)
        return res

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
                'implementation': 'no_gap'
                if self.type == 'sale'
                else 'standard',
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
                    'implementation': vals.get('implementation', 'no_gap'),
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

    # def _get_taxapps(self, perception_data, account):
    #     tax_app_obj = self.env['perception.tax.application']
    #     sit_iibb = perception_data['sit_iibb']
    #     activity_id = perception_data['activity_id']

    #     # Obtenemos la actividad configurada para esta Percepcion en el partner
    #     activity = self.env['perception.activity'].browse(activity_id)

    #     concepts = self._get_concepts_from_account(account, perception=self)

    #     # Si algun concepto no esta sujeto a percepcion, continuamos
    #     no_subject = False
    #     for concept in concepts:
    #         if concept and concept.no_subject:
    #             no_subject = True

    #     if no_subject:
    #         return

    #     concept_name = ' '.join(map(lambda a: a.name, concepts))
    #     activity_name = activity and activity.name or ''
    #     concept_ids = concepts and list(map(lambda a: a.id, concepts)) or []

    #     # Buscamos las taxapps que concuerden
    #     tapp_domain = [
    #         ('perception_tax_id', '=', self.tax_id.id),
    #         ('concept_id', 'in', concept_ids),
    #     ]
    #     if activity:
    #         tapp_domain.append(('activity_id', '=', activity and activity.id))
    #     iibb_domain = []

    #     if self.type == 'gross_income':
    #         iibb_domain.append(
    #             ('sit_iibb', '=', sit_iibb.id if sit_iibb else False)
    #         )
    #     taxapps = tax_app_obj.search(tapp_domain + iibb_domain)

    #     # Si no se encuentra con la situacion de iibb,
    #     # buscamos normalmente, aplica regla general
    #     if not taxapps:
    #         tapp_domain.append(('sit_iibb', '=', False))
    #         taxapps = tax_app_obj.search(tapp_domain)

    #     if not taxapps:
    #         raise ValidationError(
    #             _(
    #                 "Perception Error!\n"
    #                 "There is no configured a Perception Application (%(perc_name)s) "
    #                 "that corresponds to\nActivity: %(activity_name)s\n"
    #                 "Concept: %(concept_name)s\n for "
    #                 "the Account %(acc_name)s",
    #                 perc_name=self.name,
    #                 activity_name=activity_name,
    #                 concept_name=concept_name,
    #                 acc_name=account.name,
    #             )
    #         )

    #     if len(taxapps) > 1:
    #         raise ValidationError(
    #             _(
    #                 "Perception Error!\n"
    #                 "There is more than one Perception Application (%(perc_name)s) "
    #                 "that corresponds to\nActivity: %(activity_name)s\n"
    #                 "Concept: %(concept_name)s\n for "
    #                 "the Account %(acc_name)s",
    #                 perc_name=self.name,
    #                 activity_name=activity_name,
    #                 concept_name=concept_name,
    #                 acc_name=account.name,
    #             )
    #         )
    #     return taxapps

    # def _prepare_perception_vals(
    #     self, concept_id, vals, origin, origin_vals=None
    # ):
    #     origin_vals = origin_vals or {}
    #     taxapp = vals.get('tax_app_id', False)
    #     invoice = False
    #     if origin and origin._name == 'account.move':
    #         invoice = origin
    #     return {
    #         'name': self.name,
    #         'concept_id': concept_id,
    #         'invoice_id': invoice.id if invoice else False,
    #         'base': vals['base'],
    #         'amount': vals['amount'],
    #         'manual': False,  # La creamos por sistema
    #         'reg_code': vals['reg_code'],
    #         'tax_app_id': taxapp.id if taxapp else taxapp,
    #         'perception_id': self.id,
    #         'state_id': self.state_id and self.state_id.id or False,
    #         'partner_id': invoice.partner_id.id if invoice else False,
    #     }

    # @api.model
    # def compute_perception(
    #     self,
    #     perception_data,
    #     partner,
    #     origin,
    #     origin_vals=None,
    #     address_shipping=False,
    # ):
    #     origin_vals = origin_vals or {}
    #     perception_id = perception_data['perception']
    #     # Chequeamos si la Percepcion tiene seteado un state_id, que coincida
    #     # con el state_id de la direccion de entrega del partner.
    #     # Sino no se realiza la Percepcion
    #     partner_model = self.env['res.partner']
    #     destination_shipping = address_shipping or partner_model.browse(
    #         partner.address_get(['delivery']).get('delivery')
    #     )
    #     source_shipping = self.env.user.company_id.partner_id
    #     applicable = perception_id.check_applicable(
    #         sit_iibb=perception_data['sit_iibb'],
    #         from_padron=perception_data['from_padron'],
    #         source_shipping_id=source_shipping,
    #         destination_shipping_id=destination_shipping,
    #     )
    #     if not applicable:
    #         return None

    #     new_perception_lst = []
    #     if perception_id.tax_id.apply_custom_code:
    #         self.env['perception.tax.line']

    #         perceptions = perception_id.tax_id._get_taxapps_from_code(
    #             perception_data,
    #             partner,
    #             origin,
    #             origin_vals=origin_vals,
    #         )

    #         for perception_vals in perceptions:
    #             concept_id = perception_vals.get('concept_id')
    #             if not concept_id:
    #                 raise ValidationError(
    #                     _(
    #                         "Concept must be setted in python code. Perception %s"
    #                     )
    #                     % perception_id.name
    #                 )

    #             if (
    #                 perception_vals.get('amount', 0.0) == 0.0
    #                 and perception_id.tax_id.state_id.code != 'R'
    #             ):
    #                 continue

    #             # Creamos la percepcion.tax.line
    #             perception_line_vals = perception_id._prepare_perception_vals(
    #                 concept_id,
    #                 perception_vals,
    #                 origin,
    #                 origin_vals=origin_vals,
    #             )
    #             new_perception_lst.append(perception_line_vals)
    #         return new_perception_lst

    #     # Chequeamos las percepciones a aplicar que matchean
    #     # (esto corresponde a una percepcion pero que pueden
    #     # existir varios conceptos y/o actividades)
    #     perceptions = origin._compute_base_perception(
    #         perception_id,
    #         perception_data,
    #         origin_vals=origin_vals,
    #     )
    #     # Creamos las lineas de percepcion
    #     self.env['perception.tax.line']
    #     for concept_id, vals in perceptions.items():
    #         # Aplicamos la percepcion por Concepto
    #         taxapp = vals['tax_app_id']

    #         base, amount = taxapp.apply_perception(vals, perception_data)

    #         if amount == 0.0:
    #             continue

    #         vals['amount'] = amount
    #         vals['base'] = base

    #         # Creamos la percepcion.tax.line
    #         perception_line_vals = perception_id._prepare_perception_vals(
    #             concept_id,
    #             vals,
    #             origin,
    #             origin_vals=origin_vals,
    #         )
    #         new_perception_lst.append(perception_line_vals)
    #     return new_perception_lst

    # @api.model
    # def get_applicable_perceptions(
    #     self,
    #     partner,
    #     origin,
    #     origin_vals=False,
    #     date=False,
    #     address_shipping=False,
    # ):
    #     """
    #     Compute and get perceptions from partner and date
    #     Use origin and origin_vals to compute percepction with custom values

    #     `origin_vals` will be used when calling the origin
    #     functions to have a reference in case origin is an unregistered instance.

    #     @param partner:  Partner
    #     @type  partner:  res.partner

    #     @param origin:  instance to origin model or record
    #     @type  origin:  odoo.model

    #     @param origin_vals: values to compute perceptions
    #     @type  origin_vals:  dict

    #     @return:  Perceptions vals
    #     @rtype :  dict
    #     """
    #     origin_vals = origin_vals or {}
    #     # Calculamos cada Percepcion configurada en el Partner
    #     partner_perceptions = partner._get_perceptions_to_apply(
    #         date or datetime.date.today()
    #     )
    #     perception_lst = []
    #     for partner_perc in partner_perceptions.values():
    #         excluded_percent = partner_perc['excluded_percent']

    #         # Chequeamos las fechas de eximision
    #         vdate = date or datetime.date.today()

    #         first_day_of_year = datetime.date.min.replace(
    #             year=datetime.date.today().year
    #         )
    #         last_day_of_year = datetime.date.max.replace(
    #             year=datetime.date.today().year
    #         )
    #         date_from = first_day_of_year
    #         date_to = last_day_of_year
    #         if partner_perc['ex_date_from']:
    #             date_from = partner_perc['ex_date_from']
    #         if partner_perc['ex_date_to']:
    #             date_to = partner_perc['ex_date_to']

    #         # TODO: Chequear cuando solo se llena uno de las dos fechas
    #         if (not date_from and not date_to) or (
    #             vdate >= date_from and vdate <= date_to
    #         ):
    #             if excluded_percent > 1.0 or excluded_percent < 0.0:
    #                 raise ValidationError(
    #                     _(
    #                         "Perception Configuration Error!\n"
    #                         + "Excluded percent configured has to be "
    #                         + "between 0.0 and 1.0"
    #                     )
    #                 )

    #             # Si esta totalmente eximido
    #             if excluded_percent == 1.0:
    #                 continue
    #         else:
    #             partner_perc['excluded_percent'] = 0.0
    #         new_perception_lst = self.compute_perception(
    #             partner_perc,
    #             partner,
    #             origin,
    #             origin_vals=origin_vals,
    #             address_shipping=address_shipping,
    #         )
    #         if new_perception_lst:
    #             perception_lst.extend(new_perception_lst)
    #     return perception_lst
