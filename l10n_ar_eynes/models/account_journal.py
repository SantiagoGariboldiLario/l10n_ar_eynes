import logging

from odoo import fields, models, _, api
from odoo.exceptions import ValidationError
_logger = logging.getLogger(__name__)


class FO:
    """
    Fake Object ( ͡º ͜ʖ ͡º)
    """
    id = False

    def address_get():
        return {}


class AccountJournal(models.Model):
    _name = "account.journal"
    _description = "Journal"
    _inherit = "account.journal"

    def get_default_warehouse(self):
        return self.env['stock.warehouse'].browse(1).id

    @api.model
    def _get_company(self):
        return self.env.user.company_id

    code = fields.Char(
        string='POS code',
        size=6,
        required=True,
        help="Point of sale reference code",
        default=''
    )
    denomination = fields.Selection(
        selection=[
            ("a", "A"), ("b", "B"),
            ("c", "C"), ("e", "E"),
            ('m', 'M'), ('oc', 'OC'),
            ("not_defined", "Not Defined")
        ],
        string='Denomination',
        default='not_defined'
    )
    fiscal_position_id = fields.Many2one(
        comodel_name='account.fiscal.position',
        string='Fiscal Position'
    )
    fiscal_position_ids = fields.Many2many(
        comodel_name='account.fiscal.position',
        relation='journal_fiscal_position_rel',
        column1='journal_id',
        column2='fiscal_position_id',
        string='Fiscal Positions'
    )
    activity_start_date = fields.Date(
        string="Activity Start Date",
        default=fields.date.today()
    )
    warehouse_id = fields.Many2one(
        comodel_name='stock.warehouse',
        string='Warehouse',
        default=get_default_warehouse
    )
    due_date = fields.Date(
        string='Due Date',
        help='after this expiration date, account moves are not allowed to use this journal till its extended'
    )
    type = fields.Selection(
        selection_add=[
            ('receipt', 'Receipt'),
            ('payment', 'Payment'),
            ('third_party_checks', 'Third party checks'),
            ('retentions', 'Retentions'),
            ('perceptions', 'Perceptions')
        ],
        ondelete={
            'receipt': lambda recs: recs.write({'type': 'general'}),
            'payment': lambda recs: recs.write({'type': 'general'}),
            'third_party_checks': lambda recs: recs.write({'type': 'general'}),
            'retentions': lambda recs: recs.write({'type': 'general'}),
            'perceptions': lambda recs: recs.write({'type': 'general'}),
        }
    )

    # RETENTIONS FIELDS
    tax_id = fields.Many2one(
        comodel_name='account.tax',
        string='Tax',
        domain="[('tax_group_id.name', 'in', ('Retentions', 'Retenciones')),('active', '=', True)]"
    )
    type_tax_use = fields.Selection(
        string='Tax Application',
        related='tax_id.type_tax_use',
        readonly=True,
    )
    state_id = fields.Many2one(
        related='tax_id.state_id'
    )
    priority = fields.Integer()

    @api.model
    def _get_concepts_from_account(self, retention, account):
        company = self._get_company()
        concepts = account.retention_concept_ids.filtered(
            lambda c: c.type == retention.tax_id.retention_type
            and (c.company_id.id == company.id or not c.company_id)
        )
        if not concepts:
            raise ValidationError(_(
                "Retention Error\n"
                f"Account {account.name}[{account.code}] must have "
                f"an associated concept for {retention.name}. Please configure it!"
            ))
        return concepts

    def check_applicable(
            self, sit_iibb=False, from_padron=False,
            source_shipping_id=FO(), destination_shipping_id=FO()):
        self.ensure_one()

        partner_model = self.env['res.partner']
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
            partner_state = partner_model.browse(
                destination_shipping_id.address_get(['delivery']).get('delivery')
            ).id
            if not partner_state:
                raise RetentionError(_(
                    'There is no State/Province configured for '
                    f'the Supplier while computing Retention: {self.name}'
                ))

        elif tax_id.applicable_state == 'source':
            user = self.env.user
            partner = user.company_id.partner_id
            partner_state = partner_model.browse(
                source_shipping_id.address_get(['delivery']).get('delivery')
                or partner.address_get(['delivery']).get('delivery')
            ).id

            if not partner_state:
                raise RetentionError(_(
                    'There is no State/Province configured for this Company'
                ))
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

        amount_tax = sum([ml.credit or ml.debit for ml in tax_mls])
        amount_untaxed = sum([ml.credit or ml.debit for ml in taxed_mls])
        amount_no_taxed = sum([ml.credit or ml.debit for ml in untaxed_mls])
        amount_total = sum([ml.credit or ml.debit for ml in not_payable_moves])

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

    def _compute_base_retention(
            self, move_line, factor_to_pay, factor_unrec, prev_ret_ids,
            line_type, sit_iibb, logging_messages=[], activity=None):
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
        for tax_id, mls in parsed_move['concept_lines'].items():
            for ml in mls:

                # Evitamos la linea de la deuda
                concepts = self._get_concepts_from_account(
                    retention, ml.account_id
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
                    ('concept_id', 'in', concepts.ids)
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
                    raise ValidationError(_(
                        "Retention Error!\n"
                        "There is no configured a Retention Application "
                        f"({retention.name}) that corresponds to\nActivity: {activity_name} \n"
                        f"Concept: {concept_name}\n for the Account {ml.account_id.name}"
                    ))

                if len(taxapps) > 1:
                    raise ValidationError(_(
                        "Retention Error!\n"
                        "There is more than one Retention Application "
                        f"({retention.name}) configured that corresponds to\n"
                        f"Activity: {activity_name}\nConcept: {concept_name}\n"
                        f"for the Account {ml.account_id.name}"
                    ))

                # Si ya retuvimos y esta calculado sobre
                # el montos de la factura, continuamos,
                # pero si esta calculado sobre el monto del pago
                # no retornamos porque se retiene sobre lo que se va pagando
                # asi que tenemos que tener en cuenta
                # facturas con pagos parciales
                taxapp = taxapps
                logging_messages.append(
                    "Tax Application: [id: %s ; reg_code: %s] %s" %
                    (taxapp.id, taxapp.reg_code, taxapp.concept_id.name)
                )
                if taxapp.calculation_base not in [
                        'payment_amount', 'payment_amount_untaxed'] \
                        and len(prev_ret_ids):
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
                        'payment_amount', 'payment_amount_untaxed']:
                    key = (concept, False)
                else:
                    key = (concept, invoice)

                base_to_pay = round(base / factor_to_pay, 2)
                base_unrec = round(base / factor_unrec, 2)
                retentions.setdefault(key, {
                    'base': 0.0,
                    'base_to_pay': 0.0,
                    'base_unrec': 0.0,
                    'taxapp': taxapp,
                    'lines': self.env['account.move.line'],
                })
                retentions[key]['base'] += base
                retentions[key]['base_to_pay'] += base_to_pay
                retentions[key]['base_unrec'] += base_unrec
                retentions[key]['lines'] += ml
                logging_messages.append(
                    ("Agregando a la key %s ==> Base: %f Base "
                     + "To Pay: %f Base Unrec: %f") %
                    (key, base, base_to_pay, base_unrec)
                )

                logging_messages.append(
                    ("Subtotales %s ==> Base: %f Base To Pay: "
                     + "%f Base Unrec: %f") %
                    (key, retentions[key]['base'],
                     retentions[key]['base_to_pay'],
                     retentions[key]['base_unrec'])
                )

        # Mensajes de logging
        _logger.debug("\n\nLogging messages: ")
        for msg in logging_messages:
            _logger.debug(msg)
        return retentions

    _sql_constraints = [
        ('code_unique', 'unique(code)', 'code already exists!')
    ]


class RetentionError(Exception):
    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return self.msg

    def __repr__(self):
        return self.__str__()
