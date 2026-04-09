import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.safe_eval import safe_eval, wrap_module

_logger = logging.getLogger(__name__)


def create_diff_html(diff):
    color = ''
    if diff[0] == '+':
        color = 'green'
    elif diff[0] == '-':
        color = 'red'
    style = "style='color:%s;'" % color if color else ''
    return '<span %s>%s</span>' % (style, diff.rstrip())


class AccountTax(models.Model):
    _name = 'account.tax'
    _inherit = 'account.tax'

    afip_code = fields.Char(string="AFIP Code", size=4)
    check_sit_iibb = fields.Boolean(
        string='Check IIBB Situation',
        default=False,
        help="If checked, when IIBB situation is Multilateral, "
        + "this perception is always applicable",
    )
    is_bank_settlement = fields.Boolean('Is Bank Settlement')
    is_for_voucher_with_legend = fields.Boolean(default=False)
    always_apply_padron = fields.Boolean(
        'Always Apply from Padron',
        default=False,
        help="If checked, when the partner has a perception exception "
        + "and it was generated from a padron, this perception will be applied",
    )
    jurisdiccion = fields.Selection(
        selection=[
            ('nacional', 'Nacional'),
            ('provincial', 'Provincial'),
            ('municipal', 'Municipal'),
        ],
        string='Jurisdiccion',
        default='nacional',
    )
    state_id = fields.Many2one(
        comodel_name='res.country.state',
        string='State/Province',
        domain="[('country_id','=', country_id)]",
    )
    applicable_state = fields.Selection(
        selection=[
            ('dest', 'Destination'),
            ('source', 'Source'),
            ('always', 'Always'),
        ],
        string='Applicable State',
        default='dest',
        help="Indicates if this Perception is applicable when:\n"
        "* State/Province is equals to source address\n"
        "* State/Province is equals to destination address\n"
        "* Always",
    )
    from_register_ARBA = fields.Boolean('From ARBA Register')
    inform_arba = fields.Boolean('Inform ARBA?')
    inform_arciba = fields.Boolean(
        'Inform arciba?',
        help="Check if you want this perception to be informed to arciba authorities",
    )
    from_register_AGIP = fields.Boolean('From AGIP Register')
    retention_type = fields.Selection(
        selection=[
            ('vat', 'VAT'),
            ('gross_income', 'Gross Income'),
            ('profit', 'Profit'),
            ('suss', 'SUSS'),
            ('other', 'Other'),
        ],
        string='Type',
        help='Retention/Perception type',
    )
    retention_application_ids = fields.One2many(
        'retention.tax.application',
        'retention_tax_id',
        'Tax Application for Retentions',
    )
    sequence_to_use = fields.Many2one(
        comodel_name='ir.sequence', string='Sequence to use'
    )
    general_resolution = fields.Char('GR Number', required=False, size=64)
    notes = fields.Text('Notes')
    group_type = fields.Selection(related='tax_group_id.group_type')
    is_exempt = fields.Boolean(
        string='Exempt',
        default=False,
        help="Check this if this Tax represent Tax Exempts",
    )
    # PERCEPTION FIELDS:
    perception_application_ids = fields.One2many(
        'perception.tax.application',
        'perception_tax_id',
        'Tax Application for Perceptions',
    )
    apply_custom_code = fields.Boolean(default=False)
    python_code = fields.Text(
        string='Python Code',
        default=(
            "# Enter Python code here. Help about Python expression "
            "is available in the help tab of this document."
        ),
        help="The code will be executed to evaluate "
        "if it is appropriate to apply perception",
        track_visibility='onchange',
    )

    # ==================================================================================
    # v19 Migration: Override _prepare_tax_lines to modify tax dict BEFORE lines are created
    # This is cleaner than using write() after _sync_tax_lines
    #
    # LÓGICA: Interceptamos el diccionario tax_results antes de que se procese.
    # Modificamos los valores de percepciones e impuestos internos según lo ingresado
    # en perception_ids e internal_taxes_ids del move.
    # ==================================================================================
    @api.model
    def _prepare_tax_lines(self, base_lines, company, tax_lines=None):
        """
        Override to adjust perception and internal tax amounts based on
        perception_ids and internal_taxes_ids from the move.

        CAMBIO v19: En v17, _compute_all_tax modificaba el campo compute_all_tax.
        En v19, interceptamos tax_results aquí y modificamos los valores
        ANTES de que se creen las líneas de impuestos.
        """
        # 1. Call super to get the standard tax results
        tax_results = super()._prepare_tax_lines(
            base_lines, company, tax_lines=tax_lines
        )

        # 2. Get the move from the base_lines (if available)
        # base_lines es una lista de dicts que tienen 'record' apuntando al account.move.line
        if not base_lines:
            return tax_results

        # Get the first record to find the move
        first_base = base_lines[0]
        record = first_base.get('record')
        if not record or not hasattr(record, 'move_id'):
            return tax_results

        move = record.move_id
        if not move or not move.is_invoice(include_receipts=True):
            return tax_results

        # 3. Adjust perception tax amounts
        # LÓGICA ORIGINAL: Tomamos los totales de perception_ids y los usamos
        # en lugar de los valores calculados por el motor de impuestos estándar
        if hasattr(move, 'perception_ids') and move.perception_ids:
            self._adjust_perception_tax_results(move, tax_results)

        # 4. Adjust internal tax amounts (only for purchase documents)
        # LÓGICA ORIGINAL: Solo aplica para documentos de compra con impuestos internos
        if (
            move.is_purchase_document()
            and hasattr(move, 'internal_taxes_ids')
            and move.internal_taxes_ids
        ):
            self._adjust_internal_tax_results(move, tax_results)

        return tax_results

    def _adjust_perception_tax_results(self, move, tax_results):
        """
        Adjust tax_results for perceptions based on perception_ids.

        LÓGICA ORIGINAL v17: Se tomaban los valores de perception_ids.base y
        perception_ids.amount y se redistribuían en compute_all_tax.

        CAMBIO v19: Ahora modificamos directamente tax_results['tax_lines_to_add']
        y tax_results['tax_lines_to_update'].

        FIX: En v19, el grouping_key usa 'tax_repartition_line_id', no 'tax_id'.
        Debemos obtener las repartition lines de la percepción y comparar contra eso.
        """
        sign = -1 if move.is_inbound() else 1

        # Get all perception taxes from perception_ids
        for perception_line in move.perception_ids:
            perception_tax = perception_line.perception_id
            if not perception_tax:
                continue

            perception_amount = perception_line.amount

            # FIX v19: Obtener las repartition lines de la percepción
            # para poder hacer el match correcto con el grouping_key
            if move.move_type in ('out_refund', 'in_refund'):
                perception_repartition_line_ids = (
                    perception_tax.refund_repartition_line_ids.filtered(
                        lambda r: r.repartition_type == 'tax'
                    ).ids
                )
            else:
                perception_repartition_line_ids = (
                    perception_tax.invoice_repartition_line_ids.filtered(
                        lambda r: r.repartition_type == 'tax'
                    ).ids
                )

            # Check tax_lines_to_add
            # FIX: El dict tiene 'tax_repartition_line_id' como campo, no 'tax_id'
            for i, tax_vals in enumerate(
                tax_results.get('tax_lines_to_add', [])
            ):
                rep_line_id = tax_vals.get('tax_repartition_line_id')
                if (
                    rep_line_id
                    and rep_line_id in perception_repartition_line_ids
                ):
                    # CAMBIO v19: Modificamos el dict en lugar de escribir al campo
                    # Usamos el monto de perception_ids
                    rate = move.currency_rate or 1.0
                    # Actualizamos los valores con los de la percepción ingresada
                    tax_results['tax_lines_to_add'][i]['amount_currency'] = (
                        sign * perception_amount
                    )
                    tax_results['tax_lines_to_add'][i]['balance'] = (
                        sign * perception_amount * rate
                    )

            # Check tax_lines_to_update
            for _i, (_tax_line_vals, grouping_key, amounts) in enumerate(
                tax_results.get('tax_lines_to_update', [])
            ):
                # FIX: Usamos grouping_key que tiene 'tax_repartition_line_id'
                rep_line_id = (
                    grouping_key.get('tax_repartition_line_id')
                    if isinstance(grouping_key, dict)
                    else None
                )
                if (
                    rep_line_id
                    and rep_line_id in perception_repartition_line_ids
                ):
                    # CAMBIO v19: Modificamos el dict amounts
                    rate = move.currency_rate or 1.0
                    amounts['amount_currency'] = sign * perception_amount
                    amounts['balance'] = sign * perception_amount * rate

    def _adjust_internal_tax_results(self, move, tax_results):
        """
        Adjust tax_results for internal taxes based on internal_taxes_ids.

        LÓGICA ORIGINAL v17: Igual que percepciones pero para impuestos internos.
        FIX: Usar tax_repartition_line_id en lugar de tax_id.
        """
        sign = -1 if move.is_inbound() else 1

        for internal_line in move.internal_taxes_ids:
            internal_tax = internal_line.tax_id
            if not internal_tax:
                continue

            internal_amount = internal_line.amount

            # FIX v19: Obtener las repartition lines del impuesto interno
            # IMPORTANTE: Refunds (NC) usan refund_repartition_line_ids
            if move.move_type in ('out_refund', 'in_refund'):
                internal_repartition_line_ids = (
                    internal_tax.refund_repartition_line_ids.filtered(
                        lambda r: r.repartition_type == 'tax'
                    ).ids
                )
            else:
                internal_repartition_line_ids = (
                    internal_tax.invoice_repartition_line_ids.filtered(
                        lambda r: r.repartition_type == 'tax'
                    ).ids
                )

            # Check tax_lines_to_add
            # FIX: El dict tiene 'tax_repartition_line_id' como campo
            for i, tax_vals in enumerate(
                tax_results.get('tax_lines_to_add', [])
            ):
                rep_line_id = tax_vals.get('tax_repartition_line_id')
                if rep_line_id and rep_line_id in internal_repartition_line_ids:
                    rate = move.currency_rate or 1.0
                    tax_results['tax_lines_to_add'][i]['amount_currency'] = (
                        sign * internal_amount
                    )
                    tax_results['tax_lines_to_add'][i]['balance'] = (
                        sign * internal_amount / rate
                    )

            # Check tax_lines_to_update
            for _i, (tax_line_vals, _grouping_key, amounts) in enumerate(
                tax_results.get('tax_lines_to_update', [])
            ):
                tax_line_record = tax_line_vals.get('record')
                if (
                    tax_line_record
                    and tax_line_record.tax_line_id == internal_tax
                ):
                    rate = move.currency_rate or 1.0
                    amounts['amount_currency'] = sign * internal_amount
                    amounts['balance'] = sign * internal_amount / rate

    def _check_syntax_python_code(self):
        for reg in self:
            # if reg.type != 'gross_income':
            #     continue
            try:
                safe_eval(
                    reg.python_code.strip(),
                    {},
                    mode="exec",
                )
            except SyntaxError as e:
                raise ValidationError(
                    _("Error checking the syntax of the python code: \n %s")
                    % str(e)
                ) from e
            except Exception as e:
                _logger.warning(str(e))

    @api.model
    def get_taxpayer_type(self, cuit, state):
        partner = self.env['res.partner'].search(
            [
                ('vat', '=', str(cuit)),
                ('gross_income_ids', '!=', False),
            ]
        )
        if len(partner) > 1:
            partner = partner.filtered(
                lambda x: x.company_type == 'company',
            )
        if len(partner) > 1:
            raise ValidationError(
                _(
                    "Error to compute perception: \n"
                    "There are multiple partners with cuit %s"
                )
                % cuit
            )
        if not partner:
            return False
        if isinstance(state, str):
            states = partner.gross_income_ids.mapped('province_id')
            state = states.filtered(
                lambda x: x.name == state.strip(),
            )
        if len(state) > 1:
            raise ValidationError(
                _(
                    "Error to compute perception: \n"
                    "Multiple states passed: %s"
                )
                % ', '.join(state.mapped('name'))
            )
        res = partner.gross_income_ids.filtered(
            lambda x: x.province_id.id == state.id,
        )
        if len(res) > 1:
            raise ValidationError(
                _(
                    "Error to compute perception: \n"
                    "Multiple IIBB configurations for"
                    "partner: %(partner)s - state %(state)s",
                    partner=partner.name,
                    state=state.name,
                )
            )
        return res.type_taxpayer

    def _get_eval_code_context(self):
        return {
            'env': self.env,
            'uid': self.env.user.id,
            'user': self.env.user,
            'datetime': wrap_module(
                __import__('datetime'),
                [
                    'date',
                    'datetime',
                    'time',
                    'timedelta',
                    'timezone',
                    'tzinfo',
                    'MAXYEAR',
                    'MINYEAR',
                ],
            ),
            'get_taxpayer_type': self.get_taxpayer_type,
            'ValidationError': ValidationError,
            'print': print,
        }

    def _prepare_vals_from_origin(self, partner, origin, origin_vals=None):
        """
        Returns the values to compute the taxapps.
        In the python code avoid using origin, since it may come empty
        """
        origin_vals = origin_vals or {}
        if origin._name == 'account.move':
            invoice_vals = self._parse_move_lines(origin)
            origin_vals.update(
                {
                    **invoice_vals,
                    'invoice_date': origin.invoice_date,
                }
            )
        return {
            'origin': origin,
            'origin_name': origin._name,
            'partner': partner,
            **origin_vals,
        }

    def calculate_python_custom_tax(
        self,
        partner,
        origin,
        origin_vals=None,
        perc_data=None,
    ):
        """
        Execute the python code to know
        if any perception has to be applied

        @param perc_data: Data managed in current action
        that must be updated to safe_context (perception_data)
        @type  param:  dict

        @return:  Dictionary with tax to apply
        @rtype :  dict
        """
        self.ensure_one()
        origin_vals = origin_vals or {}
        perc_data = perc_data or {}
        eval_context = self._get_eval_code_context()
        # Pasamos el parent partner como variable en caso de
        # que exista para poder tomar sus percepciones
        if not partner.is_company and partner.parent_id:
            partner = partner.parent_id

        origin_eval_ctx = self._prepare_vals_from_origin(
            partner, origin, origin_vals
        )
        eval_context.update(
            {
                **origin_eval_ctx,
                'perc_data': perc_data,
                'perception': self,
                'retention': self,
                'partner': partner,
            }
        )
        try:
            safe_eval(
                self.python_code.strip(),
                eval_context,
                mode="exec",
            )
        except ValidationError as e:
            raise e
        except Exception as e:
            raise ValidationError(
                _(
                    "Error while evaluating perception %(name)s python code:\n %(err)s",
                    name=self.name,
                    err=str(e),
                )
            ) from e
        taxapp_lst = eval_context.get('result', [])
        if not taxapp_lst:
            return []
        if isinstance(taxapp_lst, dict):
            taxapp_lst = [taxapp_lst]
        return taxapp_lst

    def get_grouping_key(self, invoice_tax_val):
        """Returns a string that will be used to group account.move.line
        sharing the same properties"""
        self.ensure_one()
        return (
            str(invoice_tax_val['tax_id'])
            + '-'
            + str(invoice_tax_val['account_id'])
            + '-'
            + str(invoice_tax_val['account_analytic_id'])
            + '-'
            + str(invoice_tax_val.get('analytic_tag_ids', []))
        )

    def compute_all(
        self,
        price_unit,
        currency=None,
        quantity=1.0,
        product=None,
        partner=None,
        is_refund=False,
        handle_price_include=True,
        include_caba_tags=False,
        rounding_method=None,
        fixed_multiplicator=1,  # retained for backward compat with legacy calls
    ):
        res = super().compute_all(
            price_unit=price_unit,
            currency=currency,
            quantity=quantity,
            product=product,
            partner=partner,
            is_refund=is_refund,
            handle_price_include=handle_price_include,
            include_caba_tags=include_caba_tags,
            rounding_method=rounding_method,
        )
        res_tax_vals = res.get('taxes', [])
        for res_tax in res_tax_vals:
            tax = self.env['account.tax'].browse(res_tax['id'])
            if tax:
                res_tax.update(
                    {
                        'tax_group_name': tax.tax_group_id.name,
                        'is_exempt': tax.is_exempt,
                    }
                )
        return res

    def get_perception_account(self, is_refund):
        tax_repartition_lines = (
            is_refund
            and self.refund_repartition_line_ids
            or self.invoice_repartition_line_ids
        ).filtered(lambda x: x.repartition_type == 'tax')

        if not tax_repartition_lines:
            raise ValidationError(_("No tax repartition lines where found"))

        if len(tax_repartition_lines) != 1:
            raise ValidationError(
                _("There should only be one repartition line")
            )

        return tax_repartition_lines[0].account_id

    def get_retention_account(self):
        tax_repartition_lines = self.invoice_repartition_line_ids.filtered(
            lambda x: x.repartition_type == 'tax' and x.account_id
        )
        if not tax_repartition_lines:
            raise ValidationError(
                _(
                    "No tax repartition lines account where found for '%(ret_name)s'\n"
                    "Add one on Taxes > '%(ret_name)s' > Invoice Repartition Lines",
                    ret_name=self.name,
                )
            )

        if len(tax_repartition_lines) != 1:
            raise ValidationError(
                _("There should only be one repartition line for '%s'")
                % self.name
            )
        return tax_repartition_lines[0].account_id

    @api.model
    def _get_concepts_from_account(
        self, account, retention=None, perception=None
    ):
        company = self.env.company
        err_title = "Retention Error\n"
        if retention:
            concepts = account.retention_concept_ids.filtered(
                lambda c: c.type == retention.retention_type
                and (c.company_id.id == company.id or not c.company_id)
            )
        if perception:
            concepts = account.perception_concept_ids.filtered(
                lambda c: c.type == perception.retention_type
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
                    "%(error)s"
                    "Account %(account_name)s[%(account_code)s] must have "
                    "an associated concept for %(tax)s. Please configure it!",
                    error=err_title,
                    account_name=account.name,
                    account_code=account.code,
                    tax=tax_name,
                )
            )
        return concepts

    # pylint: disable-next=dangerous-default-value
    def _compute_base_retention(
        self,
        payment,
        move_line,
        factor_to_pay,
        factor_unrec,
        prev_ret_ids,
        line_type,
        sit_iibb,
        activity=None,
    ):
        tax_app_obj = self.env['retention.tax.application']
        retention = self

        move = move_line.move_id
        if (
            move.voucher_type_id
            in [
                self.env.ref('l10n_ar_eynes.factura_a_con_leyenda'),
                self.env.ref('l10n_ar_eynes.nota_debito_a_con_leyenda'),
                self.env.ref('l10n_ar_eynes.nota_credito_a_con_leyenda'),
            ]
            and not retention.is_for_voucher_with_legend
            and retention.retention_type in ['vat', 'profit']
        ):
            _logger.info(
                f"El comprobante {move.name} es A con leyenda, "
                "la retencion no aplica."
            )
            return {}
        if (
            move.voucher_type_id
            not in [
                self.env.ref('l10n_ar_eynes.factura_a_con_leyenda'),
                self.env.ref('l10n_ar_eynes.nota_debito_a_con_leyenda'),
                self.env.ref('l10n_ar_eynes.nota_credito_a_con_leyenda'),
            ]
            and retention.is_for_voucher_with_legend
        ):
            _logger.info(
                f"El comprobante {move.name} es A, "
                f"la retencion {retention.name} no aplica."
            )
            return {}

        # Obtenemos el concepto desde la cuenta contable
        _logger.info(
            "Parseando lineas del asiento: %s [%s]" % (move.name, move.ref)
        )
        parsed_move = self._parse_move_lines(move)

        # Por cada linea, nos fijamos la configuracion del producto
        mls = parsed_move.get("concept_lines")
        if not mls:
            _logger.warning(
                "No hay importe neto gravado al cual aplicar Retenciones. VERIFICAR FACTURA."
            )
        retentions = {}
        for ml in mls:
            # Evitamos la linea de la deuda
            concepts = self._get_concepts_from_account(
                ml.account_id, retention=retention
            )

            _logger.info(f"Linea: {ml.name} [{ml.account_id.name}]")

            # Si el concepto no esta sujeto a retencion, continuamos
            no_subject = False
            for concept in concepts:
                if concept and concept.no_subject:
                    _logger.info(
                        f"Concepto no sujeto a Retencion: {concept.name}"
                    )
                    no_subject = True

            if no_subject:
                continue

            concept_name = (" ").join([c.name for c in concepts])
            activity_name = activity and activity.name or ''

            # Buscamos las taxapps que concuerden
            tapp_domain = [
                ('retention_tax_id', '=', retention.id),
                ('concept_id', 'in', concepts.ids),
            ]
            if activity:
                tapp_domain.append(
                    ('activity_id', '=', activity and activity.id)
                )
            iibb_domain = []
            if retention.retention_type == 'gross_income':
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
                        "(%(retention_name)s) that corresponds to\n"
                        "Activity: %(activity)s \n"
                        "Concept: %(concept)s\n"
                        "for the Account %(account_name)s",
                        retention_name=retention.name,
                        activity=activity_name,
                        concept=concept_name,
                        account_name=ml.account_id.name,
                    )
                )

            if len(taxapps) > 1:
                raise ValidationError(
                    _(
                        "Retention Error!\n"
                        "There is more than one Retention Application "
                        "(%(retention_name)s) configured that corresponds to\n"
                        "Activity: %(activity)s\nConcept: %(concept)s\n"
                        "for the Account %(account_name)s",
                        retention_name=retention.name,
                        activity=activity_name,
                        concept=concept_name,
                        account_name=ml.account_id.name,
                    )
                )

            # Si ya retuvimos y esta calculado sobre
            # el montos de la factura, continuamos,
            # pero si esta calculado sobre el monto del pago
            # no retornamos porque se retiene sobre lo que se va pagando
            # asi que tenemos que tener en cuenta
            # facturas con pagos parciales
            taxapp = taxapps
            _logger.info(
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
            base = abs(
                ml.amount_currency * payment.payment_rate
                if payment.is_multi_currency
                else ml.balance
            )
            _logger.info(f"Base tomada: {base}")
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
            _logger.info(
                (
                    "Agregando a la key %s ==> Base: %f Base "
                    + "To Pay: %f Base Unrec: %f"
                )
                % (key, base, base_to_pay, base_unrec)
            )

            _logger.info(
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

        return retentions

    def _parse_move_lines(self, move):
        tax_mls = move.invoice_line_ids.filtered(lambda ml: ml.tax_line_id)
        taxed_mls = move.invoice_line_ids.filtered(lambda ml: ml.tax_ids)
        untaxed_mls = move.invoice_line_ids.filtered(
            lambda ml: not (ml.tax_line_id + ml.tax_ids)
        )

        amount_tax = sum(ml.price_subtotal for ml in tax_mls)
        amount_untaxed = sum(ml.price_subtotal for ml in taxed_mls)
        amount_no_taxed = sum(ml.price_subtotal for ml in untaxed_mls)
        amount_total = sum(ml.price_subtotal for ml in move.invoice_line_ids)

        tax_lines = {
            at: tax_mls.filtered(lambda ml: ml.tax_line_id == at)
            for at in [at for at in tax_mls.mapped('tax_line_id')]
        }
        # concept_lines = {
        #     at: taxed_mls.filtered(lambda ml: at in ml.tax_ids)
        #     for at in [at for at in taxed_mls.mapped('tax_ids')]
        # }

        result = {
            'amount_untaxed': amount_untaxed,
            'amount_tax': amount_tax,
            'amount_no_taxed': amount_no_taxed,
            'amount_total': amount_total,
            'concept_lines': taxed_mls + untaxed_mls,
            'tax_lines': tax_lines,
        }
        return result

    def check_applicable(
        self,
        sit_iibb=False,
        from_padron=False,
        source_shipping_id=False,
        destination_shipping_id=False,
    ):
        self.ensure_one()

        Partner = self.env['res.partner']

        if not self.active:
            return False

        if not self.state_id:
            return True
        if self.applicable_state == 'always':
            return True

        if self.always_apply_padron and from_padron:
            return True

        # Chequeamos la situacion de IIBB, si es CM,
        # directamente retornamos True
        if self.check_sit_iibb:
            _logger.info("Chequeo de situacion IIBB activado")
            multilateral = self.env.ref(
                "l10n_ar_eynes.iibb_situation_multilateral"
            )
            if sit_iibb == multilateral:
                _logger.info(
                    "Partner es Convenio Multilateral, "
                    f"aplica Retencion {self.name}"
                )
                return True

        partner_state = False
        retention_state = self.state_id.id

        if self.applicable_state == 'dest':
            partner_state = Partner.browse(
                destination_shipping_id.address_get(['delivery']).get(
                    'delivery'
                )
            ).state_id.id
            if not partner_state:
                raise UserError(
                    _(
                        "There is no State/Province configured for the Supplier "
                        "while computing Retention: %s"
                    )
                    % self.name
                )

        elif self.applicable_state == 'source':
            user = self.env.user
            partner = user.company_id.partner_id
            partner_state = Partner.browse(
                source_shipping_id.address_get(['delivery']).get('delivery')
                or partner.address_get(['delivery']).get('delivery')
            ).state_id.id

            if not partner_state:
                raise UserError(
                    _('There is no State/Province configured for this Company')
                )
        # Hacemos el chequeo de los states
        return retention_state == partner_state

    def _get_associated_percentage(self, invoice, perc_id):
        if not perc_id:
            return 0

        # Get base from query to prevent unwanted field recompute
        percentage = 0
        associated = (
            invoice.associated_inv_ids[0]
            if invoice.associated_inv_ids
            else False
        )
        if associated:
            query = """
                    SELECT amount, base
                    FROM perception_tax_line
                    WHERE invoice_id = %s
                    AND perception_id = %s
                    """
            self.env.cr.execute(query, (associated._origin.id, perc_id))
            res = self.env.cr.dictfetchone()
            if res:
                base = res.get("base", 0)
                amount = res.get("amount", 0)
                if base > 0:
                    percentage = amount / base
        return percentage

    # def _message_create(self, values_list):
    # model = values_list.get('model', None)
    # if model and model == 'account.tax':
    # python_code_id = (
    # self.env['ir.model.fields']
    # .search(
    # [('name', '=', 'python_code'), ('model', '=', self._name)]
    # )
    # .id
    # )
    # tracking_value_ids = values_list.get('tracking_value_ids', [])
    # diffs = []
    # for values in tracking_value_ids:
    # if values[2].get('field', 0) == python_code_id:
    # old_value = (
    # values[2]
    # .get('old_value_text', '')
    # .splitlines(keepends=True)
    # )
    # new_value = (
    # values[2]
    # .get('new_value_text', '')
    # .splitlines(keepends=True)
    # )
    # d = difflib.Differ()
    # result = list(d.compare(old_value, new_value))
    # for diff in result:
    # if diff[0] in ['+', '-', '?']:
    # diffs.append(create_diff_html(diff))
    # body = "<strong style='padding:4px'>Diffs:</strong> <br/>"
    # values_list['body'] = body + ' <br/> '.join(diff for diff in diffs)
    # return super(AccountTax, self)._message_create(values_list)
