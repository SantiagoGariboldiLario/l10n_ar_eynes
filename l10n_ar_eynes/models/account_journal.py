import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class AccountJournal(models.Model):
    _name = "account.journal"
    _description = "Journal"
    _inherit = "account.journal"

    def get_default_warehouse(self):
        return self.env['stock.warehouse'].browse(1).id

    @api.model
    def _get_company(self):
        return self.env.user.company_id

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
        ]
    )
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
        help='after this expiration date, account moves are not allowed '
        'to use this journal till its extended',
    )
    type = fields.Selection(
        selection_add=[
            ('receipt', 'Receipt'),
            ('payment', 'Payment'),
            ('third_party_checks', 'Third party checks'),
            ('retentions', 'Retentions'),
            ('perceptions', 'Perceptions'),
        ],
        ondelete={
            'receipt': lambda recs: recs.write({'type': 'general'}),
            'payment': lambda recs: recs.write({'type': 'general'}),
            'third_party_checks': lambda recs: recs.write({'type': 'general'}),
            'retentions': lambda recs: recs.write({'type': 'general'}),
            'perceptions': lambda recs: recs.write({'type': 'general'}),
        },
    )
    fcred_is_fce_emitter = fields.Boolean(string='FCE Emitter?', default=False)

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

    @api.depends('type')
    def _compute_default_account_type(self):
        super(AccountJournal, self)._compute_default_account_type()
        default_account_id_types = {
            'receipt': 'account.data_account_type_revenue',
            'payment': 'account.data_account_type_expenses',
        }

        for journal in self.filtered(
            lambda j: j.type in ('payment', 'receipt')
        ):
            if journal.type in default_account_id_types:
                journal.default_account_type = self.env.ref(
                    default_account_id_types[journal.type]
                ).id
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
                        "one PoS per shop with FCE Enabled. %s"
                    )
                    % self.shop_id
                )

    def get_pos_number(self):
        denomination = dict(self._fields['denomination'].selection).get(
            self.denomination
        )
        return self.code.strip(denomination)

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
        res -= self.env.ref(
            'account_check_printing.account_payment_method_check'
        )
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
                    'prefix': vals.get('prefix', self.get_pos_number() + '-'),
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
            return self.cn_sequence_id
        elif invoice.move_type == 'out_invoice':
            if invoice.debit_origin_id or invoice.is_debit_note:
                return self.dn_sequence_id
            return self.sequence_id

    @api.model
    def _get_concepts_from_account(
        self, account, retention=None, perception=None
    ):
        company = self._get_company()
        err_title = "Retention Error\n"
        if retention:
            concepts = account.retention_concept_ids.filtered(
                lambda c: c.type == retention.tax_id.retention_type
                and (c.company_id.id == company.id or not c.company_id)
            )
        if perception:
            concepts = account.perception_concept_ids.filtered(
                lambda c: c.type == perception.tax_id.retention_type
                and (c.company_id.id == company.id or not c.company_id)
            )
            err_title = "Perception Error\n"
        if not concepts:
            tax_name = ''
            if retention:
                tax_name = retention.name
            if perception:
                tax_name = perception.name
            raise ValidationError(
                _(
                    f"{err_title}"
                    f"Account {account.name}[{account.code}] must have "
                    f"an associated concept for {tax_name}. Please configure it!"
                )
            )
        return concepts

    def check_applicable(
        self,
        sit_iibb=False,
        from_padron=False,
        source_shipping_id=False,
        destination_shipping_id=False,
    ):
        self.ensure_one()

        Partner = self.env['res.partner']
        tax_id = self.tax_id

        if not tax_id.state_id:
            return True
        if tax_id.applicable_state == 'always':
            return True

        if tax_id.always_apply_padron and from_padron:
            return True

        # Chequeamos la situacion de IIBB, si es CM,
        # directamente retornamos True
        if tax_id.check_sit_iibb:
            _logger.info("Chequeo de situacion IIBB activado")
            multilateral = self.env.ref("iibb_situation_multilateral")
            if sit_iibb == multilateral:
                _logger.info(
                    "Partner es Convenio Multilateral, "
                    f"aplica Retencion {self.name}"
                )
                return True

        partner_state = False
        retention_state = tax_id.state_id.id

        if tax_id.applicable_state == 'dest':
            partner_state = Partner.browse(
                destination_shipping_id.address_get(['delivery']).get(
                    'delivery'
                )
            ).state_id.id
            if not partner_state:
                raise RetentionError(
                    _(
                        'There is no State/Province configured for '
                        f'the Supplier while computing Retention: {self.name}'
                    )
                )

        elif tax_id.applicable_state == 'source':
            user = self.env.user
            partner = user.company_id.partner_id
            partner_state = Partner.browse(
                source_shipping_id.address_get(['delivery']).get('delivery')
                or partner.address_get(['delivery']).get('delivery')
            ).state_id.id

            if not partner_state:
                raise RetentionError(
                    _('There is no State/Province configured for this Company')
                )
        # Hacemos el chequeo de los states
        return retention_state == partner_state

    def _parse_move_lines(self, move):
        not_payable_moves = move.line_ids.filtered(
            lambda ml: ml.account_id.internal_type != 'payable'
        )
        tax_mls = not_payable_moves.filtered(lambda ml: ml.tax_line_id)
        taxed_mls = not_payable_moves.filtered(lambda ml: ml.tax_ids)
        untaxed_mls = not_payable_moves.filtered(
            lambda ml: not (ml.tax_line_id + ml.tax_ids)
        )

        amount_tax = sum(ml.credit or ml.debit for ml in tax_mls)
        amount_untaxed = sum(ml.credit or ml.debit for ml in taxed_mls)
        amount_no_taxed = sum(ml.credit or ml.debit for ml in untaxed_mls)
        amount_total = sum(ml.credit or ml.debit for ml in not_payable_moves)

        tax_lines = {
            at: tax_mls.filtered(lambda ml: ml.tax_line_id == at)
            for at in [at for at in tax_mls.mapped('tax_line_id')]
        }
        concept_lines = {
            at: taxed_mls.filtered(lambda ml: at in ml.tax_ids)
            for at in [at for at in taxed_mls.mapped('tax_ids')]
        }

        result = {
            'amount_untaxed': amount_untaxed,
            'amount_tax': amount_tax,
            'amount_no_taxed': amount_no_taxed,
            'amount_total': amount_total,
            'concept_lines': concept_lines,
            'tax_lines': tax_lines,
        }
        return result

    # pylint: disable-next=dangerous-default-value
    def _compute_base_retention(
        self,
        move_line,
        factor_to_pay,
        factor_unrec,
        prev_ret_ids,
        line_type,
        sit_iibb,
        logging_messages,
        activity=None,
    ):
        tax_app_obj = self.env['retention.tax.application']
        retention = self

        # Por cada linea, nos fijamos la configuracion del producto
        retentions = {}

        move = move_line.move_id
        parsed_move = self._parse_move_lines(move)

        # Obtenemos el concepto desde la cuenta contable
        logging_messages.append(
            "Parseando lineas del asiento: %s [%s]" % (move.name, move.ref)
        )
        for _tax_id, mls in parsed_move['concept_lines'].items():
            for ml in mls:
                # Evitamos la linea de la deuda
                concepts = self._get_concepts_from_account(
                    ml.account_id, retention=retention
                )

                logging_messages.append(
                    f"Linea: {ml.name} [{ml.account_id.name}]"
                )

                # Si el concepto no esta sujeto a retencion, continuamos
                no_subject = False
                for concept in concepts:
                    if concept and concept.no_subject:
                        logging_messages.append(
                            f"Concepto no sujeto a Retencion: {concept.name}"
                        )
                        no_subject = True

                if no_subject:
                    continue

                concept_name = (" ").join([c.name for c in concepts])
                activity_name = activity and activity.name or ''

                # Buscamos las taxapps que concuerden
                tapp_domain = [
                    ('retention_tax_id', '=', retention.tax_id.id),
                    ('concept_id', 'in', concepts.ids),
                ]
                if activity:
                    tapp_domain.append(
                        ('activity_id', '=', activity and activity.id)
                    )
                iibb_domain = []
                if retention.type == 'gross_income':
                    iibb_domain.append(
                        ('sit_iibb', '=', sit_iibb.id if sit_iibb else False)
                    )
                taxapps = tax_app_obj.search(tapp_domain + iibb_domain)

                # Si no se encuentra con la situacion de iibb,
                # buscamos normalmente, aplica regla general
                if not taxapps:
                    tapp_domain.append(('sit_iibb', '=', False))
                    taxapps = tax_app_obj.search(tapp_domain)

                if not taxapps:
                    raise ValidationError(
                        _(
                            "Retention Error!\n"
                            "There is no configured a Retention Application "
                            f"({retention.name}) that corresponds to\n"
                            "Activity: {activity_name} \n"
                            f"Concept: {concept_name}\n"
                            f"for the Account {ml.account_id.name}"
                        )
                    )

                if len(taxapps) > 1:
                    raise ValidationError(
                        _(
                            "Retention Error!\n"
                            "There is more than one Retention Application "
                            f"({retention.name}) configured that corresponds to\n"
                            f"Activity: {activity_name}\nConcept: {concept_name}\n"
                            f"for the Account {ml.account_id.name}"
                        )
                    )

                # Si ya retuvimos y esta calculado sobre
                # el montos de la factura, continuamos,
                # pero si esta calculado sobre el monto del pago
                # no retornamos porque se retiene sobre lo que se va pagando
                # asi que tenemos que tener en cuenta
                # facturas con pagos parciales
                taxapp = taxapps
                logging_messages.append(
                    "Tax Application: [id: %s ; reg_code: %s] %s"
                    % (taxapp.id, taxapp.reg_code, taxapp.concept_id.name)
                )
                if taxapp.calculation_base not in [
                    'payment_amount',
                    'payment_amount_untaxed',
                ] and len(prev_ret_ids):
                    continue

                # Obtenemos toda la info contable de la linea de factura
                # todas las cantidades y los impuestos de IVA aplicados
                # OJO: Solo los de IVA y de cada linea en particular.
                # Esto no nos trae
                # ninguna informacion con respecto a Percepciones

                # Hacemos el computo de la Retencion por linea de factura
                base = ml.credit or ml.debit
                logging_messages.append(f"Base tomada: {base}")
                if line_type == 'income':
                    base *= -1

                # Luego vamos agrupando por Concepto y
                # Factura (no por actividad)
                # TODO: Deberiamos tener alguna configuracion
                # para agrupar o no por factura tambien
                invoice = ml.move_id or False

                concept = taxapp.concept_id
                if taxapp.calculation_base in [
                    'payment_amount',
                    'payment_amount_untaxed',
                ]:
                    key = (concept, False)
                else:
                    key = (concept, invoice)

                base_to_pay = round(base / factor_to_pay, 2)
                base_unrec = round(base / factor_unrec, 2)
                retentions.setdefault(
                    key,
                    {
                        'base': 0.0,
                        'base_to_pay': 0.0,
                        'base_unrec': 0.0,
                        'taxapp': taxapp,
                        'lines': self.env['account.move.line'],
                    },
                )
                retentions[key]['base'] += base
                retentions[key]['base_to_pay'] += base_to_pay
                retentions[key]['base_unrec'] += base_unrec
                retentions[key]['lines'] += ml
                logging_messages.append(
                    (
                        "Agregando a la key %s ==> Base: %f Base "
                        + "To Pay: %f Base Unrec: %f"
                    )
                    % (key, base, base_to_pay, base_unrec)
                )

                logging_messages.append(
                    (
                        "Subtotales %s ==> Base: %f Base To Pay: "
                        + "%f Base Unrec: %f"
                    )
                    % (
                        key,
                        retentions[key]['base'],
                        retentions[key]['base_to_pay'],
                        retentions[key]['base_unrec'],
                    )
                )

        # Mensajes de logging
        _logger.debug("\n\nLogging messages: ")
        for msg in logging_messages:
            _logger.debug(msg)
        return retentions

    def _get_taxapps(self, perception_data, account):
        tax_app_obj = self.env['perception.tax.application']
        sit_iibb = perception_data['sit_iibb']
        activity_id = perception_data['activity_id']

        # Obtenemos la actividad configurada para esta Percepcion en el partner
        activity = self.env['perception.activity'].browse(activity_id)

        concepts = self._get_concepts_from_account(account, perception=self)

        # Si algun concepto no esta sujeto a percepcion, continuamos
        no_subject = False
        for concept in concepts:
            if concept and concept.no_subject:
                no_subject = True

        if no_subject:
            return

        concept_name = ' '.join(map(lambda a: a.name, concepts))
        activity_name = activity and activity.name or ''
        concept_ids = concepts and list(map(lambda a: a.id, concepts)) or []

        # Buscamos las taxapps que concuerden
        tapp_domain = [
            ('perception_tax_id', '=', self.tax_id.id),
            ('concept_id', 'in', concept_ids),
        ]
        if activity:
            tapp_domain.append(('activity_id', '=', activity and activity.id))
        iibb_domain = []

        if self.type == 'gross_income':
            iibb_domain.append(
                ('sit_iibb', '=', sit_iibb.id if sit_iibb else False)
            )
        taxapps = tax_app_obj.search(tapp_domain + iibb_domain)

        # Si no se encuentra con la situacion de iibb,
        # buscamos normalmente, aplica regla general
        if not taxapps:
            tapp_domain.append(('sit_iibb', '=', False))
            taxapps = tax_app_obj.search(tapp_domain)

        if not taxapps:
            raise ValidationError(
                _(
                    "Perception Error!\n"
                    "There is no configured a Perception Application (%(perc_name)s) "
                    "that corresponds to\nActivity: %(activity_name)s\n"
                    "Concept: %(concept_name)s\n for "
                    "the Account %(acc_name)s",
                    perc_name=self.name,
                    activity_name=activity_name,
                    concept_name=concept_name,
                    acc_name=account.name,
                )
            )

        if len(taxapps) > 1:
            raise ValidationError(
                _(
                    "Perception Error!\n"
                    "There is more than one Perception Application (%(perc_name)s) "
                    "that corresponds to\nActivity: %(activity_name)s\n"
                    "Concept: %(concept_name)s\n for "
                    "the Account %(acc_name)s",
                    perc_name=self.name,
                    activity_name=activity_name,
                    concept_name=concept_name,
                    acc_name=account.name,
                )
            )
        return taxapps

    @api.model
    def _compute_base_perception(self, perception_data, invoice):
        if not invoice:
            return {}
        percent = perception_data['percent']

        concept_id = False

        # Por cada linea, nos fijamos la configuracion del producto
        perceptions = {}
        for line in invoice.invoice_line_ids:
            taxapps = self._get_taxapps(perception_data, line.account_id)
            if taxapps is None:
                continue

            concept_id = taxapps.concept_id.id

            # Obtenemos toda la info contable de la linea de factura
            # todas las cantidades y los impuestos de IVA aplicados
            res = line._compute_all_vat_taxes()[line.id]

            # Hacemos el computo de la Percepcion por linea de factura
            base = taxapps.compute_base(percent, res)

            if base == 0.0:
                continue
            # Modificamos la base para que se calcule con el cambio de divisa
            if not invoice.is_company_cur:
                base = base * invoice.currency_rate

            # Luego vamos agrupando por Concepto (no por actividad)
            if concept_id in perceptions:
                perceptions[concept_id]['base'] += base
                # perceptions[concept_id]['amount'] += amount
                perceptions[concept_id]['lines'].append(line.id)
            else:
                perceptions[concept_id] = {
                    'base': base,
                    # 'amount': amount,
                    'lines': [line.id],
                    'reg_code': taxapps.reg_code,
                    'tax_app_id': taxapps,
                }
        return perceptions

    def _prepare_perception_vals(self, concept_id, vals, invoice):
        taxapp = vals['tax_app_id']
        return {
            'name': self.name,
            'concept_id': concept_id,
            'invoice_id': invoice.id if invoice else False,
            'base': vals['base'],
            'amount': vals['amount'],
            'manual': False,  # La creamos por sistema
            'reg_code': vals['reg_code'],
            'tax_app_id': taxapp.id,
            'perception_id': self.id,
            'state_id': self.state_id and self.state_id.id or False,
            'partner_id': invoice.partner_id.id if invoice else False,
        }


class RetentionError(Exception):
    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return self.msg

    def __repr__(self):
        return self.__str__()
