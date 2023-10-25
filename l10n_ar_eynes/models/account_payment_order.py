import logging
from pprint import pformat as pf

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import RedirectWarning, UserError, ValidationError
from odoo.tools import float_compare

_logger = logging.getLogger(__name__)


class AccountPaymentOrder(models.Model):
    _name = 'account.payment.order'
    _description = 'Account payment order'
    _inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin']
    _rec_name = 'number'
    _order = 'date DESC'

    def default_narration(self):
        return self.env.context.get('narration', False)

    def default_partner(self):
        return self.env.context.get('partner_id', False)

    def default_reference(self):
        return self.env.context.get('reference', False)

    def default_journal(self):
        res = False
        ttype = self.env.context.get('type', 'bank')
        company = self.default_company()

        # Pago inmediato, al contado, desde el boton de la factura
        immediate = self.env.context.get('immediate_payment', False)

        if not immediate and ttype in ('payment', 'receipt'):
            rec = self.env['account.journal'].search(
                [('type', '=', ttype), ('company_id', '=', company.id)],
                limit=1,
                order='priority',
            )
            if not rec:
                action = self.env.ref('account.action_account_journal_form')
                msg = 'Cannot find a Payment/Receipt journal. \
                \nPlease create at least one.'
                raise RedirectWarning(
                    msg, action.id, _('Go to the journal configuration')
                )
            res = rec[0] or False
        return res and res.id

    def domain_journal(self):
        domain = [('id', '=', -1)]
        journals = []
        filtered_journals = self.env['account.journal'].search(
            [
                ('type', '=', self.env.context.get('type', 'bank')),
                ('company_id', '=', self.default_company().id),
            ]
        )
        for journal in filtered_journals:
            journals.append(journal.id)
        if journals:
            domain = [('id', 'in', journals)]
            return domain
        return domain

    def default_amount(self):
        self.env.context.get('amount', 0.0)

    def default_type(self):
        return self.env.context.get('type', False)

    def default_company(self):
        company = self.env['res.company']._company_default_get(
            'account.payment.order'
        )
        return company

    def default_payment_rate_currency(self):
        """
        Return the default value for field payment_rate_currency_id:
          the currency of the journal
        if there is one, otherwise the currency of the user's company
        """
        journal_obj = self.env['account.journal']
        journal_id = self.env.context.get('journal_id', False)
        if journal_id:
            journal = journal_obj.browse(journal_id)
            if journal.currency:
                return journal.currency
        # No journal given in the context, use company currency as default
        return self.env.user.company_id.currency_id

    number = fields.Char(string='Number', copy=False)
    name = fields.Char(string='Memo', default='')
    narration = fields.Text(string='Notes', default=default_narration)
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Partner',
        default=default_partner,
        states={'cancel': [('readonly', True)], 'posted': [('readonly', True)]},
    )
    account_id = fields.Many2one(
        comodel_name='account.account',
        string='Account',
    )
    pay_now = fields.Selection(
        selection=[
            ('pay_now', 'Pay Directly'),
            ('pay_later', 'Pay Later or Group Funds'),
        ],
        default='pay_now',
        string='Payment',
    )
    reference = fields.Char(string='Ref #', default=default_reference)
    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Journal',
        required=True,
        domain=domain_journal,
        default=default_journal,
        states={'cancel': [('readonly', True)], 'posted': [('readonly', True)]},
    )
    move_id = fields.Many2one(
        comodel_name='account.move',
        string='Account Entry',
        copy=False,
        readonly=True,
    )
    move_line_ids = fields.One2many(
        comodel_name='account.move.line',
        related='move_id.line_ids',
        string='Journal Items',
    )
    date = fields.Date(
        string='Date',
        default=lambda self: self._context.get(
            'date', fields.Date.context_today(self)
        ),
        states={
            'cancel': [('readonly', True)],
            'posted': [('readonly', True)],
        },
    )
    date_due = fields.Date(string="Due Date")
    state = fields.Selection(
        string='Status',
        selection=[
            ('draft', 'Draft'),
            ('cancel', 'Cancelled'),
            ('proforma', 'Pro-forma'),
            ('posted', 'Posted'),
        ],
        default='draft',
        readonly=True,
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        compute='_compute_default_journal_currency',
    )
    amount = fields.Float(
        string='Tax Amount',
        digits='Account',
        default=default_amount,
        required=True,
    )
    writeoff_acc_id = fields.Many2one(
        comodel_name='account.account',
        string='Counterpart Account',
    )
    comment = fields.Char(
        string='Counterpart Comment',
        default='Write-Off',
        required=True,
    )
    analytic_id = fields.Many2one(
        comodel_name='account.analytic.account',
        string='Write-Off Analytic Account',
    )
    writeoff_amount = fields.Float(
        string='Difference Amount',
        compute='_compute_writeoff_amount',
        readonly=True,
        help="Computed as the difference between the amount stated "
        "in the voucher and the sum of allocation on the voucher lines.",
    )
    type = fields.Selection(
        string='Default Type',
        selection=[
            ('sale', 'Sale'),
            ('purchase', 'Purchase'),
            ('payment', 'Payment'),
            ('receipt', 'Receipt'),
        ],
        default=default_type,
    )
    tax_id = fields.Many2one(
        comodel_name='account.tax',
        string='Tax',
        readonly=True,
        domain=[('price_include', '=', False)],
        help="Only for tax excluded from price",
    )
    payment_option = fields.Selection(
        string='Payment Difference',
        required=True,
        selection=[
            ('without_writeoff', 'Keep Open'),
            ('with_writeoff', 'Reconcile Payment Balance'),
        ],
        default='without_writeoff',
        help="This field helps you to choose what you want "
        + "to do with the eventual difference between the paid "
        + "amount and the sum of allocated amounts. You can either "
        + "choose to keep open this difference on the partner's "
        + "account, or reconcile it with the payment(s)",
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        default=default_company,
        required=True,
        readonly=True,
    )
    company_currency = fields.Many2one(
        related='company_id.currency_id', string='Primary currency'
    )
    pre_line = fields.Boolean(string='Previous Payments ?')
    payment_mode_line_ids = fields.One2many(
        comodel_name='account.payment.mode.line',
        inverse_name='payment_order_id',
        string='Payments Lines',
        states={
            'cancel': [('readonly', True)],
            'posted': [('readonly', True)],
        },
    )
    line_ids = fields.One2many(
        comodel_name='account.payment.order.line',
        inverse_name='payment_order_id',
        string='Payment Lines',
    )
    income_line_ids = fields.One2many(
        comodel_name='account.payment.order.line',
        inverse_name='payment_order_id',
        string='Credits',
        domain=[('type', '=', 'income')],
        context={'default_type': 'income'},
        states={
            'cancel': [('readonly', True)],
            'posted': [('readonly', True)],
        },
    )
    debt_line_ids = fields.One2many(
        comodel_name='account.payment.order.line',
        inverse_name='payment_order_id',
        string='Debits',
        domain=[('type', '=', 'debt')],
        context={'default_type': 'debt'},
        states={
            'cancel': [('readonly', True)],
            'posted': [('readonly', True)],
        },
    )
    payment_rate_currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Payment Rate Currency',
        default=default_payment_rate_currency,
        required=True,
        states={
            'cancel': [('readonly', True)],
            'posted': [('readonly', True)],
        },
    )
    payment_rate = fields.Float(
        string='Exchange Rate',
        digits=(12, 6),
        required=True,
        default=1.0,
        help="The specific rate that will be used, in "
        + "this voucher, between the selected currency "
        + "(in 'Payment Rate Currency' field) and the "
        + "voucher currency.",
    )
    paid_amount_in_company_currency = fields.Float(
        string='Paid Amount in Company Currency',
        compute='_compute_paid_amount_in_company_currency',
        readonly=True,
    )
    is_multi_currency = fields.Boolean(
        string='Multi Currency Voucher',
        compute='_compute_is_multicurrency',
        help="Fields with internal purpose only that depicts "
        "if the voucher is a multi currency one or not",
    )
    invoice_ids = fields.Many2many(
        comodel_name='account.move',
        compute='_compute_invoice_ids',
        string='Invoices',
        readonly=True,
    )
    message = fields.Char()
    # CHECKS FIELDS
    issued_check_ids = fields.One2many(
        comodel_name='account.check',
        inverse_name='payment_order_id',
        string='Issued Checks',
        required=False,
        domain=[('internal_type', '=', 'issued')],
        states={
            'cancel': [('readonly', True)],
            'posted': [('readonly', True)],
        },
    )
    issued_check_line_ids = fields.One2many(
        comodel_name='account.payment.order.issued.check.line',
        inverse_name='payment_order_id',
        string='Issued Checks',
        states={
            'cancel': [('readonly', True)],
            'posted': [('readonly', True)],
        },
    )
    third_party_check_receipt_ids = fields.One2many(
        comodel_name='account.check',
        inverse_name='source_payment_order_id',
        string='Third party checks',
        required=False,
        domain=[('internal_type', '=', 'third_party')],
        states={
            'cancel': [('readonly', True)],
            'posted': [('readonly', True)],
        },
    )
    third_party_check_ids = fields.Many2many(
        comodel_name='account.check',
        relation='third_check_voucher_rel',
        column1='dest_payment_order_id',
        column2='third_check_id',
        string='Third Checks',
        states={
            'cancel': [('readonly', True)],
            'posted': [('readonly', True)],
        },
    )
    # RETENTION FIELDS
    retention_ids = fields.One2many(
        comodel_name='account.payment.order.retention.line',
        inverse_name='payment_order_id',
        string='Retentions',
        readonly=True,
        states={
            'draft': [('readonly', False)],
        },
    )
    date_effective = fields.Date(
        string='Effective Date',
        help="This is the effective date when one give this voucher "
        "to the Supplier",
    )
    receipt_number = fields.Char(
        string='Supplier Receipt Number',
        size=32,
        help="This is the number of the receipt given by the Supplier",
    )
    disable_retentions = fields.Boolean(
        string='Disable Retentions',
        help="Check this if you want to disable automatic "
        "calculation of retention on this payment",
    )
    # OTHER PAYMENTS FIELDS
    concept_line_ids = fields.One2many(
        comodel_name='account.payment.order.concept.line',
        inverse_name='payment_order_id',
        string="Other Concepts",
    )
    other_payment = fields.Boolean(string='Other Payments')
    employee_id = fields.Many2one('hr.employee', string="Employee")
    employee_payment = fields.Boolean(string='Employee Payments')

    def prepare_retention_values(self, voucher):
        ret_vals = {
            'voucher_number': voucher.number,
            'partner_id': voucher.partner_id.id,
        }
        return ret_vals

    @api.onchange('retention_ids')
    def _onchange_retentions(self):
        amount = self.payment_order_amount_hook()
        self.amount = amount

    @api.onchange(
        'third_party_check_ids',
        'third_party_check_receipt_ids',
        'issued_check_line_ids',
    )
    def onchange_checks(self):
        amount = self.payment_order_amount_hook()
        self.amount = amount

    def payment_order_amount_hook(self):
        amount = self.get_payment_lines_amount()
        amount += self.get_issued_checks_amount()
        amount += self.get_third_party_checks_amount()
        amount += self.get_third_party_check_receipts_amount()
        amount += self.get_retentions_amount()
        if (
            any(
                self.debt_line_ids.mapped('amount')
                + self.income_line_ids.mapped('amount')
            )
            or not amount
            or self.disable_retentions
        ):
            return amount
        amount += self.compute_advance_payment_retentions(amount)
        return amount

    def get_issued_checks_amount(self):
        return sum(self.issued_check_line_ids.mapped('amount'))

    def get_third_party_checks_amount(self):
        return sum(self.third_party_check_ids.mapped('amount'))

    def get_third_party_check_receipts_amount(self):
        return sum(self.third_party_check_receipt_ids.mapped('amount'))

    def get_retentions_amount(self):
        return sum(self.retention_ids.mapped('amount'))

    def compute_advance_payment_retentions(self, amount):
        amount = amount - sum(self.retention_ids.mapped('amount'))
        new_ret_amount = 0.0
        if not amount:
            self.retention_ids = False
            return amount
        tax_app_obj = self.env['retention.tax.application']
        partner_retentions = self.partner_id._get_retentions_to_apply(self.date)
        create_vals = []
        for advance_ret in self.partner_id.advance_retention_ids:
            if (advance_ret.retention_id, advance_ret.concept_id) in [
                (rtl.retention_id, rtl.concept_id) for rtl in self.retention_ids
            ]:
                continue
            ret_vals = partner_retentions.get(advance_ret.retention_id.id)
            if not ret_vals:
                raise ValidationError(
                    _(
                        f"Retention {advance_ret.retention_id.name} "
                        "is not configured for Partner "
                        f"Fiscal Position {self.partner_id.property_account_position_id.name}"
                    )
                )
            taxapp = tax_app_obj.search(
                [
                    # ('retention_tax_id', '=', advance_ret.retention_id.id),
                    # TODO check if need to use this field in the domain
                    ('concept_id', '=', advance_ret.concept_id.id),
                    ('company_id', '=', self.company_id.id),
                ]
            )
            if not taxapp:
                raise ValidationError(
                    _(
                        "Retention Error!\n"
                        "There is no configured a Retention Application "
                        f"({advance_ret.retention_id.name}) "
                        f"that corresponds to Concept: {advance_ret.concept_id.name}"
                    )
                )
            if len(taxapp) > 1:
                raise ValidationError(
                    _(
                        "Retention Error!\n"
                        "There is more than one Retention Application "
                        f"({advance_ret.retention_id.name}) configured "
                        f"that corresponds to Concept: {advance_ret.concept_id.name}"
                    )
                )
            vals = {
                'base': amount,
                'to_pay': amount,
            }
            base, amount = taxapp.apply_retention(
                self.partner_id,
                ret_vals.get('percent'),
                ret_vals.get('excluded_percent'),
                vals,
                self.date,
            )
            if not amount:
                continue
            retention_line_vals = self._prepare_advanced_payment_retention(
                advance_ret, taxapp, ret_vals, base, amount
            )
            create_vals.append(retention_line_vals)
            new_ret_amount += amount
            _logger.info("Retentions to create 2: %s" % pf(retention_line_vals))
        if create_vals:
            self.retention_ids = [(0, 0, val) for val in create_vals]
        return new_ret_amount

    def _prepare_advanced_payment_retention(
        self, advance_ret, taxapp, ret_vals, base, amount
    ):
        retention_line_vals = {
            'name': advance_ret.retention_id.name,
            'concept_id': advance_ret.concept_id.id,
            'date': self.date,
            'account_id': advance_ret.retention_id.tax_id.account_id.id,
            'base': base,
            'amount': amount,
            'manual': False,
            'retention_id': advance_ret.retention_id.id,
            'certificate_no': '',
            'taxapp_id': taxapp.id,
            'reg_code': taxapp.reg_code,
            'state_id': advance_ret.retention_id.tax_id.state_id.id,
            'excluded_percent': ret_vals.get('excluded_percent'),
            'exclusion_date_certificate': ret_vals.get(
                'exclusion_date_certificate'
            ),
        }
        return retention_line_vals

    def recompute_voucher_lines(
        self, partner_id, journal_id, price, currency_id, ttype, date
    ):
        res = super(AccountPaymentOrder, self).recompute_voucher_lines(
            partner_id, journal_id, price, currency_id, ttype, date
        )

        # Si es un pago, quitamos todo el calculo de imputacion automatica
        # porque interfiere en el calculo de retenciones automaticas
        if ttype == 'payment' and not self._context.get('immediate_payment'):
            all_l = res['value']['line_cr_ids'] + res['value']['line_dr_ids']
            for line in all_l:
                line['amount'] = 0.0
                line['reconcile'] = False
        return res

    def calculate_retentions(self):
        self.ensure_one()
        retentions = {}
        # Computamos todas las retenciones para el voucher
        partner_retentions = self.partner_id._get_retentions_to_apply(self.date)

        for partner_ret in list(partner_retentions.values()):
            excluded_percent = partner_ret.get('excluded_percent')
            if excluded_percent == 1.0:
                continue

            res = self.calculate_single_retention(partner_ret)

            # Generamos la key
            for ret in res:
                key = (
                    ret['retention_id'],
                    ret['concept_id'],
                )
                if key not in retentions:
                    retentions[key] = ret
                else:
                    raise Warning(
                        _(
                            'Something is wrong with retention calculation '
                            'because there are more than one tuple (voucher '
                            'line, retention, concept) applied to this voucher'
                        )
                    )

        return list(retentions.values())

    def calculate_single_retention(self, retention_data):
        self.ensure_one()
        partner_model = self.env['res.partner']
        retention = retention_data.get('retention')
        activity = retention_data.get('activity_id')
        percent = retention_data.get('percent')
        excluded_percent = retention_data.get('excluded_percent')
        exclusion_date_certificate = retention_data.get(
            'exclusion_date_certificate'
        )
        sit_iibb = retention_data.get('sit_iibb')
        from_padron = retention_data.get('from_padron')

        res = []

        logging_messages = []
        all_concepts = {}

        logging_messages.append("\n\nAplicando %s ==>" % (self.name))
        logging_messages.append(
            f"Actividad: {activity} "
            f"Porcentaje en partner: {percent}. "
            f"Porcentaje de Exclusion: {excluded_percent}"
        )
        for po_line in [
            line
            for line in (self.income_line_ids + self.debt_line_ids)
            if line.amount
        ]:
            # Chequeamos si la Retencion tiene seteado un state_id,
            # que coincida con el state_id de la direccion de
            # entrega del partner. Sino no se realiza # la Retencion
            invoice = po_line.move_invoice_id
            destination_shipping = (
                invoice.address_shipping_id
                or partner_model.browse(
                    invoice.partner_id.address_get(['delivery']).get('delivery')
                )
            )
            source_shipping = self.env.user.company_id.partner_id
            applicable = retention.check_applicable(
                sit_iibb=sit_iibb,
                from_padron=from_padron,
                source_shipping_id=source_shipping,
                destination_shipping_id=destination_shipping,
            )
            if not applicable:
                continue

            move_line = po_line.move_line_id

            # Chequeamos si la factura que corresponde a esta move_line ya
            # tiene una retencion aplicada previa de este tipo en algun pago
            # parcial previo.
            # Por lo tanto, no corresponde retener nuevamente porque sino
            # estariamos aplicando dos veces la misma
            # retencion sobre el pago de una misma factura
            prev_ret_ids = self._check_previous_retentions(retention, move_line)

            # Agrupamos por retencion y concepto antes de aplicar la retencion
            # O sea, vamos a calcular las bases para cada
            # (retencion,concepto) y luego aplicamos la retencion

            # Obtenemos el factor desde el total de la deuda contra
            # lo que se pretende pagar
            mla = move_line.credit or move_line.debit
            factor_to_pay = mla / po_line.amount
            factor_unrec = mla / po_line.amount_unreconciled

            logging_messages.append("Linea a aplicar %s" % (po_line.ref))

            retentions = retention._compute_base_retention(
                move_line,
                factor_to_pay,
                factor_unrec,
                prev_ret_ids,
                po_line.type,
                sit_iibb,
                activity=activity,
                logging_messages=logging_messages,
            )

            for (concept, _invoice), vals in retentions.items():
                # Agrupamos por concepto y factura
                key = (retention.id, concept)
                all_concepts.setdefault(
                    key,
                    {
                        'base': 0.0,
                        'to_pay': 0.0,
                        'taxapp': vals['taxapp'],
                        'move_lines': self.env['account.move.line'],
                    },
                )
                all_concepts[key]['base'] += vals['base_unrec']
                all_concepts[key]['to_pay'] += vals['base_to_pay']

                # Agregamos la move_line.
                # En realidad nos interesa la voucher_line,
                # pero a estas alturas todavia no la tenemos
                if move_line not in all_concepts[key]['move_lines']:
                    all_concepts[key]['move_lines'] += move_line

        # Ahora que tenemos las bases agrupadas por concepto
        # aplicamos el calculo de la retencion
        for (_ret, concept), vals in all_concepts.items():
            taxapp = vals['taxapp']
            base, amount = taxapp.apply_retention(
                move_line.partner_id,
                percent,
                excluded_percent,
                vals,
                self.date,
            )
            all_concepts[key]['amount'] = amount

            if amount == 0.0:
                continue

            # Creamos las lineas de retencion
            # Creamos la retention.tax.line
            retention_line_vals = {
                'name': retention.name,
                'move_line_ids': [(6, 0, all_concepts[key]['move_lines'].ids)],
                'concept_id': concept.id,
                'date': self.date,
                'account_id': retention.tax_id.get_retention_account().id,
                'base': base,
                'amount': amount,
                'manual': False,  # La creamos por sistema
                'retention_id': retention.id,
                'certificate_no': '',
                'taxapp_id': taxapp.id,
                'reg_code': taxapp.reg_code,
                'state_id': retention.state_id.id,
                'excluded_percent': excluded_percent,
                'exclusion_date_certificate': exclusion_date_certificate,
            }
            _logger.info(f'retention created: {pf(retention_line_vals)}')
            res.append(retention_line_vals)
        return res

    def _check_previous_retentions(self, retention, move_line=False):
        sql = """
        SELECT rl.id FROM account_journal r
        JOIN account_payment_order_retention_line rl ON r.id=rl.retention_id
        JOIN retention_line_move_line_rel rv ON rv.retention_line_id=rl.id
        JOIN account_move_line ml ON ml.id=rv.move_line_id
        JOIN account_payment_order po ON po.id=rl.payment_order_id
        JOIN account_payment_order_line pol
            ON pol.move_line_id=ml.id
            AND pol.payment_order_id=po.id
        JOIN account_move mv ON mv.id=ml.move_id
        WHERE r.id=%(ret_id)s AND po.state='posted'
            AND (r.company_id = %(company_id)s OR r.company_id IS NULL)
        """

        company = self.default_company()

        q_params = {
            'ret_id': retention.id,
            'company_id': company.id,
        }
        if move_line:
            q_params['move_line_id'] = move_line.id
            sql += " AND ml.id=%(move_line_id)s"

        self.env.cr.execute(sql, q_params)
        res = self.env.cr.fetchall()

        line_ids = [r[0] for r in res]
        return line_ids

    def action_clean_lines(self):
        """reset income and debt lines"""
        for rec in self:
            rec.income_line_ids = [(5, 0, 0)]
            rec.debt_line_ids = [(5, 0, 0)]
            rec.message = ''

    @api.onchange('journal_id')
    def _onchange_journal_id(self):
        self._payment_rate()
        self.action_clean_lines()

    # @api.depends('date')
    # def _compute_period(self):
    #     for rec in self:
    #         if not rec.date:
    #             continue
    #         period_obj = rec.env['date.period']
    #         period = period_obj._get_period(rec.date)
    #         rec.period_id = period.id

    @api.onchange('date')
    def _payment_rate(self):
        rate = self.currency_id._get_rates(self.company_id, self.date)[
            self.currency_id.id
        ]

        if (
            hasattr(self.currency_id, 'preciated')
            and self.currency_id.preciated
        ):
            rate = 1 / rate

        self.payment_rate = rate

    @api.depends('income_line_ids.invoice_id', 'debt_line_ids.invoice_id')
    def _compute_invoice_ids(self):
        for payment in self:
            income_invs = payment.income_line_ids.mapped('invoice_id')
            debt_invs = payment.debt_line_ids.mapped('invoice_id')
            payment.invoice_ids = income_invs + debt_invs

    @api.depends('journal_id', 'company_id')
    def _compute_default_journal_currency(self):
        for payment in self:
            payment.currency_id = (
                payment.journal_id.currency_id or payment.company_id.currency_id
            )

    @api.depends(
        'debt_line_ids', 'income_line_ids', 'amount', 'concept_line_ids'
    )
    def _compute_writeoff_amount(self):
        for po in self:
            writeoff_amount = po._get_writeoff_amount_hook()
            currency = po.currency_id or po.company_id.currency_id
            po.writeoff_amount = currency.round(writeoff_amount)

    def _get_writeoff_amount_hook(self):
        self.ensure_one()
        debit = credit = 0.0
        sign = self.type == 'payment' and -1 or 1
        for line in self.debt_line_ids:
            debit += line.amount
        for line in self.income_line_ids:
            credit += line.amount
        amount = self.amount - sign * (credit - debit)
        amount -= self.get_concept_lines_amount()
        return amount

    def get_concept_lines_amount(self):
        return sum(self.concept_line_ids.mapped('amount'))

    @api.depends('amount')
    def _compute_paid_amount_in_company_currency(self):
        """Returns the same amount"""
        for p in self:
            p.paid_amount_in_company_currency = p.amount

    @api.depends('currency_id')
    def _compute_is_multicurrency(self):
        for p in self:
            p.is_multi_currency = p.currency_id != p.company_id.currency_id

    @api.onchange('partner_id')
    def onchange_partner_id(self):
        if self.journal_id.type in ('sale', 'sale_refund'):
            account_id = self.partner_id.property_account_receivable_id
        elif self.journal_id.type in ('purchase', 'purchase_refund', 'expense'):
            account_id = self.partner_id.property_account_payable_id
        elif self.type in ('sale', 'receipt'):
            account_id = self.journal_id.loss_account_id
        elif self.type in ('purchase', 'payment'):
            account_id = self.journal_id.profit_account_id
        else:
            account_id = (
                self.journal_id.profit_account_id
                or self.journal_id.loss_account_id
            )
        self.account_id = account_id

    def get_payment_lines_amount(self):
        return sum(self.payment_mode_line_ids.mapped('amount'))

    # def payment_order_amount_hook(self):
    #     amount = self.get_payment_lines_amount()
    #     return amount

    @api.onchange('payment_mode_line_ids')
    def onchange_payment_line(self):
        amount = self.payment_order_amount_hook()
        self.amount = amount

    @api.onchange('debt_line_ids')
    def onchange_debt_lines(self):
        self.recompute_payment_lines('debt_line_ids')

    @api.onchange('income_line_ids')
    def onchange_income_lines(self):
        self.recompute_payment_lines('income_line_ids')

    def unlink(self):
        self._check_retentions_unlinkable()
        if self.state not in ['draft', 'cancel']:
            raise ValidationError(
                _(
                    "Error!\nYou can't unlink a posted payment order.\n"
                    "First you should unreconcile It."
                )
            )
        for voucher in self:
            if voucher.type == 'receipt':
                voucher.third_party_check_ids.unlink()
            voucher.issued_check_line_ids.unlink()
        return super(AccountPaymentOrder, self).unlink()

    def _check_retentions_unlinkable(self):
        for voucher in self:
            u_rets = voucher.retention_ids.filtered(lambda x: not x.unlinkable)
            if u_rets:
                raise ValidationError(
                    _(
                        "Error!\nVoucher %(voucher_name)s [id: %(voucher_id)s] "
                        "has Unlinkable Retentions:\n%(retentions)s",
                        voucher_name=voucher.name,
                        voucher_id=voucher.id,
                        retentions=("\n").join(
                            ["%s [id: %s]" % (r.name, r.id) for r in u_rets]
                        ),
                    )
                )
        return True

    def _check_partner_set(self):
        if not self.partner_id:
            raise UserError(
                _(
                    "Error!\n"
                    "The Partner must be set to gather accounting information."
                )
            )

    def update_o2m(self, field_str, lines):
        if not hasattr(self, field_str) or not lines:
            return False
        old_lines = getattr(self, field_str)
        new_lines = [
            x
            for x in lines
            if x['move_line_id'] not in old_lines.mapped('move_line_id.id')
        ]
        setattr(self, field_str, [(0, 0, x) for x in new_lines])
        return True

    def gather_income_lines(self):
        self.ensure_one()
        self._check_partner_set()
        account_type = self.type == 'payment' and 'payable' or 'receivable'
        domain = [
            ('debit', '!=', 0),
            ('credit', '=', 0),
            ('account_id.internal_type', '=', account_type),
            ('reconciled', '=', False),
            ('partner_id', '=', self.partner_id.id),
            ('move_id.state', '=', 'posted'),
            ('currency_id', '=', self.currency_id.id),
        ]

        moves = self.env['account.move.line'].search(domain)
        lines = self._prepare_income_debt_lines('income', moves)
        return self.update_o2m('income_line_ids', lines)

    def gather_debt_lines(self):
        self.ensure_one()
        self._check_partner_set()
        account_type = self.type == 'payment' and 'payable' or 'receivable'
        domain = [
            ('debit', '=', 0),
            ('credit', '!=', 0),
            ('account_id.internal_type', '=', account_type),
            ('reconciled', '=', False),
            ('partner_id', '=', self.partner_id.id),
            ('move_id.state', '=', 'posted'),
        ]
        # if self.is_multi_currency:
        #     domain += [('currency_id', '=', self.currency_id.id)]
        # else:
        #     domain += [('currency_id', 'in', (self.currency_id.id, False))]

        moves = self.env['account.move.line'].search(domain)
        lines = self._prepare_income_debt_lines('debt', moves)
        return self.update_o2m('debt_line_ids', lines)

    def doesnt_have_residual(self, move_line):
        if move_line.reconciled:
            if self.currency_id == move_line.currency_id:
                if move_line.amount_residual_currency <= 0:
                    return True
            else:
                if move_line.amount_residual <= 0:
                    return True
        return False

    def _prepare_income_debt_lines(self, lines_type, move_lines):
        res = []
        for line in move_lines:
            line_data = {}
            if self.doesnt_have_residual(line):
                continue

            amount_original = line.debit or line.credit or 0.0
            sign = lines_type == 'debt' and -1 or 1
            amount_unreconciled = sign * line.amount_residual or 0.0

            line_data = {
                'name': line.move_id.name,
                'invoice_id': line.move_id.id,
                'move_line_id': line.id,
                'account_id': line.account_id.id,
                'amount_original': amount_original,
                'date_original': line.date,
                'date_due': line.date_maturity,
                'amount_unreconciled': amount_unreconciled,
                'currency_id': self.currency_id.id,
                'type': lines_type,
            }
            res.append(line_data)
        return res

    def recompute_payment_lines(self, onchange_attr):
        MoveLine = self.env['account.move.line']
        Currency = self.env['res.currency']

        ttype = self.env.context.get('type', 'bank')
        total_credit = total_debit = 0.0
        if ttype == 'payment':
            account_type = 'payable'
            total_debit = self.amount or 0.0
        else:
            total_credit = self.amount or 0.0
            account_type = 'receivable'

        line_ids = getattr(self, onchange_attr)
        the_line = False
        if line_ids:
            for line in line_ids:
                if (
                    line.invoice_id
                    and not line.move_line_id
                    and not line.account_id
                ):
                    the_line = line
        if not the_line:
            return
        line_ids = the_line
        if not self.env.context.get('move_line_ids', False):
            ids = MoveLine.search(
                [
                    ('account_id.internal_type', '=', account_type),
                    ('reconciled', '=', False),
                    ('partner_id', '=', self.partner_id.id),
                    ('move_id', '=', line_ids.invoice_id.id),
                ]
            )
        else:
            return

        company_currency = self.journal_id.company_id.currency_id
        invoice_id = self.env.context.get('invoice_id', False)
        account_move_lines = ids.sorted(key=lambda x: -1 * x.id)
        move_lines_found = []

        for line in account_move_lines:
            if self.doesnt_have_residual(line):
                continue

            if invoice_id:
                if line.invoice_id.id == line_ids.invoice_id.id:
                    # if the invoice linked to the voucher
                    # line is equal to the invoice_id in context
                    # then we assign the amount on that line,
                    # whatever the other voucher lines
                    move_lines_found.append(line.id)
            elif self.currency_id == company_currency:
                # otherwise treatments is the same but with other field names
                if line.amount_residual == self.amount:
                    # if the amount residual is equal the amount
                    # voucher, we assign it to that voucher line,
                    # whatever the other voucher lines
                    move_lines_found.append(line.id)
                    break
                # otherwise we will split the voucher amount
                # on each line (by most old first)
                total_credit += line.credit and line.amount_residual or 0.0
                total_debit += line.debit and line.amount_residual or 0.0
            elif self.currency_id == line.currency_id:
                if line.amount_residual_currency == self.amount:
                    move_lines_found.append(line.id)
                    break
                line_residual = Currency.with_context(
                    currency_rate=self.payment_rate
                ).compute(abs(line.amount_residual), self.currency_id)

                total_credit += line.credit and line_residual or 0.0
                total_debit += line.debit and line_residual or 0.0

        # voucher line creation
        res = self._prepare_income_debt_lines(
            onchange_attr == 'debt_line_ids' and 'debt' or 'income',
            account_move_lines,
        )

        if res:
            old_lines = getattr(self, onchange_attr)
            setattr(self, onchange_attr, [(0, 0, x) for x in res])
            setattr(
                self, onchange_attr, getattr(self, onchange_attr) + old_lines
            )
            setattr(
                self, onchange_attr, getattr(self, onchange_attr) - line_ids
            )
        else:
            setattr(self, onchange_attr, False)

    @api.onchange(
        'income_line_ids', 'debt_line_ids', 'disable_retentions', 'date'
    )
    def onchange_lines(self):
        for po in self:
            if po.type != 'payment':
                return

            po.retention_ids = [(5, 0, 0)]

            if not po.disable_retentions:
                if any(
                    self.debt_line_ids.mapped('amount')
                    + self.income_line_ids.mapped('amount')
                ):
                    vals = po.calculate_retentions()
                    po.retention_ids = [(0, 0, val) for val in vals]
                else:
                    if po.amount:
                        po.compute_advance_payment_retentions(po.amount)

    def proforma_voucher(self):
        self.ensure_one()
        for voucher in self:
            voucher.retention_ids.write(
                {
                    'unlinkable': False,
                }
            )
        # Chequeamos si la writeoff_amount no es negativa
        if round(self.writeoff_amount, 2) < 0.0:
            raise ValidationError(
                _(
                    'Error!\n Cannot validate a '
                    'voucher with negative amount.\n Please check '
                    'that Writeoff Amount is not negative.'
                )
            )
        if self.amount == 0.0 and not self._get_income_amount():
            raise ValidationError(
                _(
                    "Validate Error!\n"
                    "You cannot validate a voucher with amount of 0.0 "
                    "and no income lines"
                )
            )

        self._clean_payment_lines()
        self.action_move_line_create()

        return True

    def _get_income_amount(self):
        self.ensure_one()
        return sum(self.income_line_ids.mapped('amount'))

    def _clean_payment_lines(self):
        for payment_line in self.payment_mode_line_ids:
            if payment_line.amount == 0:
                payment_line.unlink()
        return True

    def action_move_line_create(self):
        '''
        Confirm the vouchers given in ids and create
        the journal entries for each of them
        '''
        Move = self.env['account.move']
        MoveLine = self.env['account.move.line']
        if self.move_id:
            return

        company_currency = self._get_company_currency()
        current_currency = self._get_current_currency()
        # But for the operations made by _convert_amount, we always need to give the date in the context  # noqa
        ctx = {
            'date': self.date,
            'check_move_validity': False,
        }
        # Create the account move record.
        move_recordset = Move.with_context(**ctx).create(
            self.account_move_get()
        )
        # Get the name of the account_move just created
        name = move_recordset.name
        move_id = move_recordset.id
        if self.type in ('payment', 'receipt'):
            # Creamos las lineas contables de todas las formas de pago, etc  # noqa
            move_line_vals = self.create_move_lines(
                move_id, company_currency, current_currency
            )
            line_total = 0.0
            for vals in move_line_vals:
                line_total += vals['debit'] - vals['credit']
                MoveLine.with_context(**ctx).create(vals)
        else:
            # Create the first line of the voucher
            move_line_brw = MoveLine.with_context(**ctx).create(
                self.first_move_line_get(
                    move_id, company_currency, current_currency
                )
            )
            line_total = move_line_brw.debit - move_line_brw.credit

        rec_list_ids = []
        if self.type == 'sale':
            line_total = line_total - self.amount
        elif self.type == 'purchase':
            line_total = line_total + self.amount
        # Create one move line per voucher line where amount is not 0.0
        line_total, rec_list_ids = self.with_context(
            **ctx
        ).voucher_move_line_create(
            line_total, move_id, company_currency, current_currency
        )

        # Create the writeoff line if needed
        ml_writeoff = self.writeoff_move_line_get(
            line_total, move_id, name, company_currency, current_currency
        )
        if ml_writeoff:
            MoveLine.with_context(**ctx).create(ml_writeoff)

        # We post the voucher.
        self.write(
            {
                'move_id': move_id,
                'state': 'posted',
                'number': name,
            }
        )
        move_recordset.action_post()
        # We automatically reconcile the account move lines.
        for move_lines in rec_list_ids:
            if len(move_lines) >= 2:
                move_lines.reconcile()

        # Borramos las lineas que estan en 0
        for line in self.line_ids:
            if not line.amount:
                line.unlink()
        return True

    def _get_company_currency(self):
        '''
        Get the currency of the actual company.
        :param voucher_id: Id of the voucher what
          i want to obtain company currency.
        :return: currency id of the company of the voucher
        :rtype: int
        '''
        return self.journal_id.company_id.currency_id

    def _get_current_currency(self):
        '''
        Get the currency of the voucher.
        :param voucher_id: Id of the voucher what
          i want to obtain current currency.
        :return: currency id of the voucher
        :rtype: int
        '''
        return self.currency_id or self._get_company_currency()

    def account_move_get(self):
        '''
        This method prepare the creation of the
        account move related to the given voucher.
        :param voucher_id: Id of voucher for which
         we are creating account_move.
        :return: mapping between fieldname and value of account move to create
        :rtype: dict
        '''

        if self.number:
            name = self.number
        elif self.journal_id.sequence_id:
            if not self.journal_id.sequence_id.active:
                raise UserError(
                    _(
                        'Configuration Error!\n'
                        'Please activate the sequence of selected journal!'
                    )
                )
            name = self.journal_id.sequence_id.next_by_id()
        else:
            raise UserError(
                _('Error!\n Please define a sequence on the journal.')
            )
        if not self.reference:
            ref = name.replace('/', '')
        else:
            ref = self.reference

        move = {
            'name': name,
            'journal_id': self.journal_id.id,
            'narration': self.narration,
            'date': self.date,
            'ref': ref,
        }
        return move

    def create_move_line_hook(self, move_id):
        move_lines = []

        if self.type in ('sale', 'receipt'):
            for check in self.third_party_check_receipt_ids:
                if check.amount == 0.0:
                    continue

                res = check.third_party_create_voucher_move_line(self)
                res['move_id'] = move_id
                move_lines.append(res)
                check.to_wallet()

        elif self.type in ('purchase', 'payment'):
            # Cheques recibidos de terceros que los damos a un proveedor
            for check in self.third_party_check_ids:
                if check.amount == 0.0:
                    continue

                res = check.third_party_create_voucher_move_line(self)
                res['move_id'] = move_id
                move_lines.append(res)
                check.check_delivered()

            # Cheques propios que los damos a un proveedor
            for check in self.issued_check_ids:
                if check.amount == 0.0:
                    continue

                res = check.issued_create_voucher_move_line()
                res['move_id'] = move_id
                res['issued_check_id'] = check.id
                move_lines.append(res)

                if check.type == 'postdated':
                    state = 'waiting_accreditation'
                else:
                    state = 'paid'

                vals = {
                    'issued_check_state': state,
                    'payment_move_id': move_id,
                    'receiving_partner_id': self.partner_id.id,
                }

                if not check.origin:
                    vals['origin'] = self.reference

                if not check.issue_date:
                    vals['issue_date'] = self.date
                check.write(vals)

        self.validate_retentions_sequence()
        for ret in self.retention_ids:
            res = ret.create_voucher_move_line()
            if res:
                res['move_id'] = move_id
                move_lines.append(res)

            # Write voucher values in the retention tax line using method
            ret_vals = self.prepare_retention_values(self)
            ret.write(ret_vals)
        return move_lines

    def validate_retentions_sequence(self):
        """We validate that every retention has a sequence
        before so it doesn't modify sequence number
        """
        retentions_without_sequence = self.retention_ids.mapped(
            'retention_id'
        ).filtered(lambda ret: not ret.sequence_id.id)
        if retentions_without_sequence:
            raise ValidationError(
                _("This journals doesnt have a sequence established:\n%s")
                % retentions_without_sequence.mapped('name')
            )

    @api.model
    def _convert_paid_amount_in_company_currency(self, amount):
        """Return actual amount, the user defines the rate of conversion and its result"""
        currency = self.currency_id.with_context(date=self.date)
        company_currency = self.company_id.currency_id
        res = currency.compute(amount, company_currency)
        return res

    def _create_move_line_payment(
        self,
        move_id,
        name,
        journal_id,
        amount,
        company_currency,
        amount_currency,
        current_currency,
        sign,
    ):
        # amount_in_company_currency = (
        #     self._convert_paid_amount_in_company_currency(amount)
        # )
        amount_in_company_currency = amount
        debit = credit = 0.0
        pl_account_id = journal_id.suspense_account_id.id
        if self.type in ('purchase', 'payment'):
            credit = amount_in_company_currency
        elif self.type in ('sale', 'receipt'):
            debit = amount_in_company_currency
        if debit < 0:
            credit = -debit
            debit = 0.0
        if credit < 0:
            debit = -credit
            credit = 0.0
        sign = debit - credit < 0 and -1 or 1
        move_line = {
            'name': name or '/',
            'debit': debit,
            'credit': credit,
            'account_id': pl_account_id,
            'move_id': move_id,
            'journal_id': self.journal_id.id,
            'partner_id': self.partner_id.id,
            'currency_id': company_currency != current_currency
            and current_currency.id
            or False,
            'amount_currency': company_currency != current_currency
            and sign * amount_currency
            or 0.0,
            'date': self.date,
            'date_maturity': self.date_due,
        }
        return move_line

    def create_move_lines(self, move_id, company_currency, current_currency):
        total_debit = total_credit = 0.0
        # TODO: is there any other alternative then the voucher type ??
        # ANSWER: We can have payment and receipt "In Advance".
        # TODO: Make this logic available.
        # -for sale, purchase we have but for the payment and receipt we do not have as based on the bank/cash journal we can not know its payment or receipt  # noqa
        if self.type in ('purchase', 'payment'):
            total_credit = self.paid_amount_in_company_currency
        elif self.type in ('sale', 'receipt'):
            total_debit = self.paid_amount_in_company_currency
        if total_debit < 0:
            total_credit = -total_debit
            total_debit = 0.0
        if total_credit < 0:
            total_debit = -total_credit
            total_credit = 0.0
        sign = total_debit - total_credit < 0 and -1 or 1

        # Creamos una move_line por payment_line
        move_lines = []
        for pml in self.payment_mode_line_ids:
            if pml.amount == 0.0:
                continue

            move_lines.append(
                self._create_move_line_payment(
                    move_id,
                    pml.name,
                    pml.payment_mode_id,
                    pml.amount,
                    company_currency,
                    pml.amount_currency,
                    pml.currency_id,
                    sign,
                )
            )

        # Creamos un hook para agregar los demas asientos contables de otros modulos  # noqa
        move_lines += self.create_move_line_hook(move_id)

        # Recorremos las lineas para  hacer un chequeo de debit y credit contra total_debit y total_credit  # noqa
        amount_credit = 0.0
        amount_debit = 0.0
        for line in move_lines:
            _logger.info(f"line created: {pf(line)}")
            amount_credit += line['credit']
            amount_debit += line['debit']

        if round(amount_credit, 3) != round(total_credit, 3) or round(
            amount_debit, 3
        ) != round(total_debit, 3):
            if self.type in ('purchase', 'payment'):
                amount_credit -= amount_debit
                amount_debit -= amount_debit
            else:
                amount_debit -= amount_credit
                amount_credit -= amount_credit
            if round(amount_credit, 3) != round(total_credit, 3) or round(
                amount_debit, 3
            ) != round(total_debit, 3):
                _logger.info(
                    f'amount credit:{round(amount_credit, 3)} | '
                    f'total credit:{round(total_credit, 3)}'
                )
                _logger.info(
                    f'amount debit:{round(amount_debit, 3)} | '
                    f'total debit:{round(total_debit, 3)}'
                )
                raise UserError(
                    _(
                        "Voucher Error!\n"
                        "Voucher Paid Amount and sum of different payment "
                        "mode must be equal"
                    )
                )
        return move_lines

    def first_move_line_get(self, move_id, company_currency, current_currency):
        """
        Return a dict to be use to create the
        first account move line of given voucher.
        :param voucher_id: Id of voucher what we are creating account_move.
        :param move_id: Id of account move where this line will be added.
        :param company_currency: id of currency of the
         company to which the voucher belong
        :param current_currency: id of currency of the voucher
        :return: mapping between fieldname and
         value of account move line to create
        :rtype: dict
        """
        debit = credit = 0.0
        # TODO: is there any other alternative then the voucher type ??
        # ANSWER: We can have payment and receipt "In Advance".
        # TODO: Make this logic available.
        # -for sale, purchase we have but for the payment and
        # receipt we do not have as based on the bank/cash
        # journal we can not know its payment or receipt
        if self.type in ('purchase', 'payment'):
            credit = self.paid_amount_in_company_currency
        elif self.type in ('sale', 'receipt'):
            debit = self.paid_amount_in_company_currency
        if debit < 0:
            credit = -debit
            debit = 0.0
        if credit < 0:
            debit = -credit
            credit = 0.0
        sign = debit - credit < 0 and -1 or 1
        # set the first line of the voucher
        move_line = {
            'name': self.name or '/',
            'debit': debit,
            'credit': credit,
            'account_id': self.account_id.id,
            'move_id': move_id,
            'journal_id': self.journal_id.id,
            'partner_id': self.partner_id.id,
            'currency_id': company_currency != current_currency
            and current_currency.id
            or False,
            'amount_currency': (
                sign * abs(self.amount)
                if company_currency != current_currency
                else 0.0
            ),
            'date': self.date,
            'date_maturity': self.date_due,
        }
        return move_line

    def _convert_amount(self, amount):
        return self.currency_id.compute(amount, self.company_id.currency_id)

    def _get_exchange_lines(
        self, line, move_id, amount_residual, company_currency, current_currency
    ):
        if amount_residual > 0:
            account_id = (
                line.payment_order_id.company_id.expense_currency_exchange_account_id
            )
            if not account_id:
                action_id = self.env.ref('account.action_account_form').id
                msg = _(
                    "You should configure the 'Loss Exchange Rate "
                    "Account' to manage automatically the booking of "
                    "accounting entries related to differences "
                    "between exchange rates."
                )
                raise RedirectWarning(
                    msg, action_id, _('Go to the configuration panel')
                )
        else:
            account_id = (
                line.payment_order_id.company_id.income_currency_exchange_account_id
            )
            if not account_id:
                action_id = self.env.ref('account.action_account_form').id
                msg = _(
                    "You should configure the 'Gain Exchange Rate "
                    "Account' to manage automatically the booking of "
                    "accounting entries related to differences "
                    "between exchange rates."
                )
                raise RedirectWarning(
                    msg, action_id, _('Go to the configuration panel')
                )
        # Even if the amount_currency is never filled, we need to pass the foreign currency because otherwise  # noqa
        # the receivable/payable account may have a secondary currency, which render this field mandatory  # noqa
        if line.account_id.currency_id:
            account_currency_id = line.account_id.currency_id
        else:
            account_currency_id = (
                company_currency != current_currency
                and current_currency
                or False
            )
        move_line = {
            'journal_id': line.payment_order_id.journal_id.id,
            'name': _('change') + ': ' + (line.name or '/'),
            'account_id': line.account_id.id,
            'move_id': move_id,
            'partner_id': line.payment_order_id.partner_id.id,
            'currency_id': account_currency_id.id,
            'amount_currency': 0.0,
            'quantity': 1,
            'credit': amount_residual > 0 and amount_residual or 0.0,
            'debit': amount_residual < 0 and -amount_residual or 0.0,
            'date': line.payment_order_id.date,
        }
        move_line_counterpart = {
            'journal_id': line.payment_order_id.journal_id.id,
            'name': _('change') + ': ' + (line.name or '/'),
            'account_id': account_id.id,
            'move_id': move_id,
            'amount_currency': 0.0,
            'partner_id': line.payment_order_id.partner_id.id,
            'currency_id': account_currency_id.id,
            'quantity': 1,
            'debit': amount_residual > 0 and amount_residual or 0.0,
            'credit': amount_residual < 0 and -amount_residual or 0.0,
            'date': line.payment_order_id.date,
        }
        return (move_line, move_line_counterpart)

    def voucher_move_line_create(
        self, line_total, move_id, company_currency, current_currency
    ):
        MoveLine = self.env['account.move.line']
        tot_line = line_total
        rec_lst_ids = []

        date = self.read(['date'])[0]['date']
        self = self.with_context(date=date)
        # voucher_currency = self.journal_id.currency_id or self.company_id.currency_id  # noqa
        prec = self.env['decimal.precision'].precision_get('account')
        for line in self.line_ids:
            if not line.amount and not (
                line.move_line_id
                and not float_compare(
                    line.move_line_id.debit,
                    line.move_line_id.credit,
                    precision_digits=prec,
                )
                and not float_compare(
                    line.move_line_id.debit, 0.0, precision_digits=prec
                )
            ):
                continue
            sign = line.type == 'debt' and -1 or 1
            amount = sign * (line.untax_amount or line.amount)
            # currency_rate_difference = 0.0
            if line.amount == line.amount_unreconciled:
                if not line.move_line_id:
                    raise UserError(
                        _(
                            "Wrong voucher line\n"
                            "The invoice you are willing to "
                            "pay is not valid anymore."
                        )
                    )
                # currency_rate_difference = (
                # line.move_line_id.amount_residual - amount)
            move_line_analytic_account_id = (
                line.account_analytic_id
                and line.account_analytic_id.id
                or False
            )
            move_line = {
                'journal_id': self.journal_id.id,
                'name': line.name or '/',
                'account_id': line.account_id.id,
                'move_id': move_id,
                'partner_id': self.partner_id.id,
                'currency_id': line.original_currency_id != company_currency
                and line.original_currency_id.id
                or False,
                'amount_currency': line.amount_currency
                and line.amount_currency * sign * -1
                or 0,
                'analytic_account_id': move_line_analytic_account_id,
                'quantity': 1,
                'credit': 0.0,
                'debit': 0.0,
                'date': self.date,
            }
            if amount < 0:
                amount = -amount

            if line.type == 'debt':
                tot_line += amount
                move_line['debit'] = amount
            else:
                tot_line -= amount
                move_line['credit'] = amount

            if self.tax_id and self.type in ('sale', 'purchase'):
                move_line.update(
                    {
                        'account_tax_id': self.tax_id.id,
                    }
                )
            payment_line = MoveLine.create(move_line)
            new_amls = payment_line + line.move_line_id
            if line.move_line_id.id:
                rec_lst_ids.append(new_amls)

        for line in self.concept_line_ids:
            if not line.amount:
                continue

            if line.payment_order_id.type == 'payment':
                amount = line.amount
            else:
                amount = line.amount * (-1)

            move_line = {
                'journal_id': self.journal_id.id,
                'name': line.name or '/',
                'account_id': line.account_id.id,
                'move_id': move_id,
                'partner_id': self.partner_id.id,
                'currency_id': False,
                'analytic_account_id': line.account_analytic_id
                and line.account_analytic_id.id
                or False,
                'quantity': 1,
                'credit': 0.0,
                'debit': 0.0,
                'date': self.date,
            }
            if amount < 0:
                amount = -amount
                tot_line -= amount
                move_line['credit'] = amount
            else:
                tot_line += amount
                move_line['debit'] = amount

            # Creamos la linea
            MoveLine.create(move_line)

        return (tot_line, rec_lst_ids)

    def writeoff_move_line_get(
        self, line_total, move_id, name, company_currency, current_currency
    ):
        move_line = {}

        current_currency_obj = (
            self.currency_id or self.journal_id.company_id.currency_id
        )

        if not current_currency_obj.is_zero(line_total):
            diff = line_total
            account_id = False
            write_off_name = ''
            if self.payment_option == 'with_writeoff':
                account_id = self.writeoff_acc_id.id
                write_off_name = self.comment
            elif self.partner_id:
                if self.type in ('sale', 'receipt'):
                    account_id = (
                        self.partner_id.property_account_receivable_id.id
                    )
                else:
                    account_id = self.partner_id.property_account_payable_id.id
            else:
                # fallback on account of voucher
                account_id = self.account_id.id
            sign = self.type == 'payment' and -1 or 1
            move_line = {
                'name': write_off_name or name,
                'account_id': account_id,
                'move_id': move_id,
                'partner_id': self.partner_id.id,
                'date': self.date,
                'credit': diff > 0 and diff or 0.0,
                'debit': diff < 0 and -diff or 0.0,
                'amount_currency': company_currency != current_currency
                and (sign * -1 * self.writeoff_amount)
                or 0.0,
                'currency_id': company_currency != current_currency
                and current_currency.id
                or False,
                'analytic_account_id': self.analytic_id
                and self.analytic_id.id
                or False,
            }
        return move_line

    def cancel_voucher(self):
        for payment in self:
            if payment.move_id:
                payment.move_id.line_ids.remove_move_reconcile()
                payment.move_id.button_cancel()
                payment.move_id.with_context(force_delete=True).unlink()
        self.write(
            {
                'state': 'cancel',
                'move_id': False,
            }
        )

        for voucher in self:
            # Cancelamos los cheques de tercero en recibos
            third_receipt_checks = voucher.third_party_check_receipt_ids
            third_receipt_checks.cancel_check(internal_type='third_party')

            # Volvemos a cartera los cheques de tercero en pagos
            third_checks = voucher.third_party_check_ids
            third_checks.return_wallet()

            # Cancelamos los cheques emitidos
            issued_checks = voucher.issued_check_ids
            issued_checks.cancel_check(internal_type='issued')
        return True

    def action_cancel_draft(self):
        self._check_retentions_unlinkable()
        for voucher in self:
            # A draft los cheques emitidos
            issued_checks = voucher.issued_check_ids
            issued_checks.write({'issued_check_state': 'draft'})

            # A draft los cheques de tercero en cobros
            third_checks = voucher.third_party_check_receipt_ids
            third_checks.write({'third_party_check_state': 'in_wallet'})
        self.write({'state': 'draft'})
        return True

    @api.model
    def create(self, vals_list):
        sequence_model = self.env['ir.sequence']
        if vals_list.get('type') == 'receipt':
            vals_list['number'] = sequence_model.next_by_code(
                'customer.payment.order'
            ) or _('New')
        elif vals_list.get('type') == 'payment':
            vals_list['number'] = sequence_model.next_by_code(
                'supplier.payment.order'
            ) or _('New')
        return super(AccountPaymentOrder, self).create(vals_list=vals_list)

    def is_payment(self):
        return self.type in ('purchase', 'payment')

    def is_receipt(self):
        return self.type in ('sale', 'receipt')

    _sql_constraints = [
        ("unique_number", "unique(type, number)", _("Number must be unique")),
    ]


class AccountPaymentOrderLine(models.Model):
    _name = 'account.payment.order.line'
    _description = 'voucher lines'
    _order = "move_line_id"

    name = fields.Char(string='description', default='')
    payment_order_id = fields.Many2one(
        comodel_name='account.payment.order',
        string='payment order',
        ondelete='cascade',
    )
    account_id = fields.Many2one(
        comodel_name='account.account',
        string='account',
    )
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='partner',
        related='payment_order_id.partner_id',
    )
    untax_amount = fields.Float(string='untax amount')
    amount = fields.Float(string='amount', digits='account')
    reconcile = fields.Boolean(string='full reconcile')
    type = fields.Selection(
        selection=[('debt', 'debt'), ('income', 'income')],
        string='dr/cr',
    )
    move_line_id = fields.Many2one(
        comodel_name='account.move.line', string='Journal Item', copy=False
    )
    date_original = fields.Date(
        string='Date', related='move_line_id.date', readonly=True
    )
    account_analytic_id = fields.Many2one(
        comodel_name='account.analytic.account', string='Analytic Account'
    )
    date_due = fields.Date(
        string='Due Date', related='move_line_id.date_maturity', readonly=True
    )
    amount_original = fields.Float(
        string='Original Amount',
        digits='Account',
        compute='_compute_balance',
        store=True,
    )
    amount_unreconciled = fields.Float(
        string='Open Balance',
        digits='Account',
        compute='_compute_balance',
        store=True,
    )
    amount_currency = fields.Float(string='Amount CCY', digits='Account')
    amount_original_currency = fields.Float(
        string='Original Amount CCY',
        digits='Account',
        compute='_compute_balance',
        store=True,
    )
    amount_unreconciled_currency = fields.Float(
        string='Open Balance CCY',
        digits='Account',
        compute='_compute_balance',
        store=True,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        related='payment_order_id.company_id',
        store=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        compute='_compute_currency_id',
        readonly=True,
    )
    original_currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        compute='_compute_currency_id',
        readonly=True,
    )
    invoice_id = fields.Many2one(
        comodel_name='account.move',
        string='Invoice',
        domain=[('state', '=', 'open')],
    )
    move_invoice_id = fields.Many2one(
        comodel_name='account.move', related='move_line_id.move_id'
    )
    state = fields.Selection(
        string='State', related='payment_order_id.state', readonly=True
    )
    ref = fields.Char(string='Reference', size=64)

    # @api.onchange('amount')
    # def onchange_amount(self):
    #     parent = self.payment_order_id
    #     if self.original_currency_id.id != parent.company_currency.id:
    #         amount_computed = self.amount / parent.payment_rate
    #     else:
    #         amount_computed = 0
    #     self.amount_currency = amount_computed

    @api.onchange('amount_currency')
    def onchange_amount_currency(self):
        parent = self.payment_order_id
        if self.original_currency_id.id != parent.company_currency.id:
            amount_computed = self.amount_currency * parent.payment_rate
        else:
            amount_computed = 0
        self.amount = amount_computed

    @api.depends('move_line_id')
    def _compute_balance(self):
        for line in self:
            move_line = line.move_line_id
            line.amount_original = move_line.debit or move_line.credit or 0.0
            sign = line.type == 'debt' and -1 or 1
            line.amount_unreconciled = sign * move_line.amount_residual or 0.0
            # Usability Multicurrency fields
            line.amount_original_currency = move_line.amount_currency
            line.amount_unreconciled_currency = (
                sign * move_line.amount_residual_currency
            )

    def _compute_currency_id(self):
        for line in self:
            line.original_currency_id = (
                line.payment_order_id.currency_id
                or line.payment_order_id.company_currency
            )
            if line.payment_order_id:
                # line.currency_id = line.payment_order_id.currency_id
                line.currency_id = line.payment_order_id.company_currency

    @api.onchange('reconcile')
    def amount_full_conciliation(self):
        for line in self:
            if not line.reconcile:
                line.amount = 0
                line.amount_currency = 0
            else:
                if (
                    line.original_currency_id.id
                    != line.payment_order_id.company_currency.id
                ):
                    line.amount_currency = line.amount_unreconciled_currency
                    line.amount = (
                        line.amount_unreconciled_currency
                        * line.payment_order_id.payment_rate
                    )
                else:
                    line.amount = line.amount_unreconciled
                    line.amount_currency = 0

    def _check_amount_over_original(self):
        if self.payment_order_id.is_multi_currency:
            _logger.warning(
                'Voucher is multicurrency: Ignoring _check_amount_over_original'
            )
            return None
        if not (0 <= self.amount <= self.amount_unreconciled):
            raise ValidationError(
                _(
                    "Error!\nThe amount assigned to an invoice must not excede "
                    "the unreconciled amount, nor be negative."
                )
            )

    @api.constrains('amount')
    def _check_amount(self):
        for order_line in self:
            order_line._check_amount_over_original()


class AccountPaymentModeLine(models.Model):
    _name = 'account.payment.mode.line'
    _description = 'Payment method lines'

    name = fields.Text(string='Description', help='Payment reference')
    payment_order_id = fields.Many2one(
        comodel_name='account.payment.order', string='Payment Order'
    )
    payment_mode_id = fields.Many2one(
        comodel_name='account.journal', string='Payment Method'
    )
    amount = fields.Float(
        string='Amount',
        digits=(16, 2),
        default=0.0,
        required=False,
        help='Payment amount in the company currency',
    )
    amount_currency = fields.Float(
        string='Amount in Partner Currency',
        digits=(16, 2),
        required=False,
        help='Payment amount in the partner currency',
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        default=lambda s: s._compute_currency_id(),
        string='Currency',
    )
    company_currency = fields.Many2one(
        comodel_name='res.currency',
        string='Company Currency',
        readonly=True,
        default=lambda s: s._get_company_currency(),
    )
    date = fields.Date(
        string='Payment Date', help="This date is informative only."
    )

    # @api.depends('payment_mode_id')
    # def _compute_currency(self):
    #     for i in self:
    #         i.currency_id = i.payment_mode_id.currency_id or \
    #             self._get_company_currency()

    def _compute_currency_id(self):
        return self.payment_order_id.currency_id

    @api.onchange('currency_id')
    def onchange_currency_id(self):
        parent = self.payment_order_id

        if self.currency_id.id != parent.company_currency.id:
            amount_computed = self.amount / parent.payment_rate
        else:
            amount_computed = self.amount
        self.amount_currency = amount_computed

    @api.onchange('payment_mode_id')
    def onchange_payment_mode_id(self):
        parent = self.payment_order_id
        self.currency_id = parent.currency_id or parent.company_currency

    @api.onchange('amount')
    def onchange_amount(self):
        parent = self.payment_order_id

        if self.currency_id.id != parent.company_currency.id:
            amount_computed = self.amount / parent.payment_rate
        else:
            amount_computed = self.amount

        if self.amount_currency == amount_computed:
            return
        else:
            self.amount_currency = amount_computed

    @api.model
    def _get_company_currency(self):
        currency_obj = self.env['res.currency']
        if self.env.user.company_id:
            return self.env.user.company_id.currency_id
        else:
            return currency_obj.search([('rate', '=', 1.0)], limit=1)


class AccountPaymentOrderRetentionLine(models.Model):
    _name = 'account.payment.order.retention.line'
    _description = 'Retention lines in payment order'

    def default_retention_move_lines(self):
        if (
            self.payment_order_id.disable_retentions
            or not self.is_profit_retention()
        ):
            return []
        return self.create_retention_lines()

    name = fields.Char(string='Retention', size=64)
    date = fields.Date(index=True)
    payment_order_id = fields.Many2one(
        comodel_name='account.payment.order',
        string='Payment Order',
        ondelete='cascade',
    )
    currency_id = fields.Many2one(related='payment_order_id.currency_id')
    currency_rate = fields.Float(related='payment_order_id.payment_rate')
    voucher_number = fields.Char(string='Reference', size=64)
    account_id = fields.Many2one(
        comodel_name='account.account',
        string='Tax Account',
        required=True,
        domain=[
            ('type', 'not in', ['view', 'income', 'closed']),
        ],
    )
    base = fields.Float(digits='Account')
    amount = fields.Float(digits='Account')
    base_currency = fields.Float(
        digits='Account',
        compute='_compute_base_currency',
        string='Base Currency',
    )
    amount_currency = fields.Float(
        digits='Account',
        compute='_compute_amount_currency',
        string='Amount Currency',
    )
    retention_id = fields.Many2one(
        comodel_name='account.journal',
        string='Retention Configuration',
        required=True,
        domain=[('type', '=', 'retentions')],
        help="Retention configuration used for this retention tax, where "
        "all the configuration resides. Accounts, Tax Codes, etc.",
    )
    retention_type = fields.Selection(
        string='Retention Type',
        related='retention_id.tax_id.retention_type',
    )
    base_amount = fields.Float(
        string='Base Code Amount',
        digits='Account',
    )
    tax_amount = fields.Float(
        string='Tax Code Amount',
        digits='Account',
    )
    company_id = fields.Many2one(
        string='Company',
        related='account_id.company_id',
        store=True,
        readonly=True,
    )
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Partner',
        required=False,
    )
    vat = fields.Char(
        string='CIF/NIF',
        related='partner_id.vat',
        readonly=True,
    )
    certificate_no = fields.Char(
        string='Certificate No.',
        required=False,
        size=32,
    )
    state_id = fields.Many2one(
        comodel_name='res.country.state',
        string="State/Province",
    )
    move_line_ids = fields.Many2many(
        comodel_name='account.move.line',
        relation='retention_line_move_line_rel',
        column1='retention_line_id',
        column2='move_line_id',
        string='Move Lines',
    )
    invoice_id = fields.Many2one(comodel_name='account.move', string='Invoice')
    invoice_ref = fields.Char(string='Invoice Reference', size=64)
    taxapp_id = fields.Many2one(
        comodel_name='retention.tax.application', string='Tax Application'
    )
    reg_code = fields.Integer('Reg. Code')
    date_applied = fields.Date(
        'Date Applied',
        help="This is the date of the real application of the retention",
    )
    manual = fields.Boolean('Manual', default=True)
    excluded_percent = fields.Float('Percentage of exclusion')
    exclusion_date_certificate = fields.Date(
        string='Exclusion General Resolution Date'
    )
    unlinkable = fields.Boolean('Unlinkable', default=True)
    retention_move_line_ids = fields.One2many(
        comodel_name='retention.move.line',
        inverse_name='payment_order_line_id',
        string='Retention move lines',
        default=default_retention_move_lines,
        readonly=True,
    )
    retention_move_lines_total = fields.Float(
        string='Total',
        digits='Account',
        compute='_compute_total_retention_move_lines',
    )
    concept_id = fields.Many2one(
        comodel_name='retention.concept',
        string='Concept',
        related='taxapp_id.concept_id',
    )
    concept_amount = fields.Float(
        string='Amount',
        digits='Account',
        related='taxapp_id.tax_allowance',
    )
    applied_aliquot = fields.Float(
        string='Aliquot applied',
        digits='Account',
        related='taxapp_id.percent',
    )
    total_month_retention = fields.Float(
        string='Total month retention',
        compute='_compute_total_month_retention',
        store=False,
    )
    month_applied_retentions = fields.Float(
        string='Applied retentions this month',
        compute='_compute_month_applied_retentions',
        store=False,
    )
    actual_payment_retention = fields.Float(
        string='Retention to be made in actual payment',
        compute='_compute_actual_payment_retention',
        store=False,
    )

    def create_retention_lines(self):
        """This method creates the retention move lines and return the ID's"""
        move_line_ids = []
        for move in self.get_current_month_moves():
            move_line_ids.append(self.get_retention_line_vals(move))

        po_lines = self.payment_order_id.line_ids
        for line in po_lines.filtered(lambda debtline: debtline.amount > 0):
            move_type_map = {
                'in_invoice': 'In Invoice',
                'out_invoice': 'Out Invoice',
                'in_refund': 'In Refund',
                'out_refund': 'Out Refund',
            }
            invoice = line.invoice_id
            if invoice.is_company_cur:
                total_without_vat = (
                    line.amount / invoice.amount_total * invoice.amount_untaxed
                )
            else:
                total_without_vat = (
                    (line.amount / line.payment_order_id.payment_rate)
                    / invoice.amount_total
                    * (
                        invoice.amount_untaxed
                        * line.payment_order_id.payment_rate
                    )
                )
            move_line_ids.append(
                self.env['retention.move.line'].create(
                    {
                        'payment_order_line_id': self.id,
                        'move_id': invoice.id,
                        'move_name': 'draft',
                        'move_type': move_type_map[invoice.move_type],
                        'total_without_vat': total_without_vat,
                        'payment_order_reference': self.payment_order_id.number
                        or '',
                    }
                )
            )
        if move_line_ids:
            return [rec.id for rec in move_line_ids]
        return move_line_ids

    def get_current_month_moves(self):
        return self.env['account.payment.order.line'].search(
            [
                ('payment_order_id.state', '=', 'posted'),
                ('partner_id', '=', self.payment_order_id.partner_id.id),
                ('invoice_id.payment_state', 'in', ('paid', 'partial')),
                ('invoice_id.invoice_date', '>=', self.date.replace(day=1)),
                (
                    'invoice_id.invoice_date',
                    '<=',
                    self.date + relativedelta(day=31),
                ),
            ]
        )

    def get_retention_line_vals(self, move):
        """Return move line values to insert into retention lines o2m

        Args:
            move (account.move): Invoices which values are taken

        Returns:
            dict: Dictionary with values to insert
        """
        move_type_map = {
            'in_invoice': 'In Invoice',
            'out_invoice': 'Out Invoice',
            'in_refund': 'In Refund',
            'out_refund': 'Out Refund',
        }
        invoice = move.invoice_id
        if invoice.is_company_cur:
            total_without_vat = (
                move.amount / invoice.amount_total * invoice.amount_untaxed
            )
        else:
            total_without_vat = (
                (move.amount / move.payment_order_id.payment_rate)
                / invoice.amount_total
                * (invoice.amount_untaxed * move.payment_order_id.payment_rate)
            )
        return self.env['retention.move.line'].create(
            {
                'payment_order_line_id': self.id,
                'move_id': invoice.id,
                'move_name': invoice.name,
                'move_type': move_type_map[invoice.move_type],
                'total_without_vat': total_without_vat,
                'payment_order_reference': move.payment_order_id.number or '',
            }
        )

    @api.depends('retention_move_line_ids')
    def _compute_total_retention_move_lines(self):
        for rec in self:
            rec.retention_move_lines_total = sum(
                rec.retention_move_line_ids.mapped('total_without_vat')
            )

    @api.depends(
        'retention_move_lines_total',
        'concept_amount',
        'applied_aliquot',
    )
    def _compute_total_month_retention(self):
        for rec in self:
            total = rec.retention_move_lines_total
            amount = rec.concept_amount
            total_month_retention = 0
            if total > amount:
                total_month_retention = (total - amount) * (
                    rec.applied_aliquot / 100
                )
            rec.total_month_retention = total_month_retention

    @api.depends('retention_move_line_ids', 'applied_aliquot')
    def _compute_month_applied_retentions(self):
        for rec in self:
            concept_amount = rec.concept_amount
            total = sum(
                rec.retention_move_line_ids.filtered(
                    lambda rtml: rtml.move_name != 'draft'
                ).mapped('total_without_vat')
            )
            if total == 0 or total < concept_amount:
                rec.month_applied_retentions = 0
            else:
                rec.month_applied_retentions = (total - concept_amount) * (
                    rec.applied_aliquot / 100
                )

    @api.depends('total_month_retention', 'month_applied_retentions')
    def _compute_actual_payment_retention(self):
        for rec in self:
            rec.actual_payment_retention = (
                rec.total_month_retention - rec.month_applied_retentions
            )

    @api.depends('amount', 'currency_rate')
    def _compute_amount_currency(self):
        for rec in self:
            rec.amount_currency = rec.amount / rec.currency_rate

    @api.depends('base', 'currency_rate')
    def _compute_base_currency(self):
        for rec in self:
            rec.base_currency = rec.base / rec.currency_rate

    @api.onchange('retention_id')
    def onchange_retention_id(self):
        res = {}
        if self.retention_id:
            self.account_id = self.retention_id.tax_id.get_retention_account()
            self.name = self.retention_id.name
            res['domain'] = {
                'concept_id': [
                    ('type', '=', self.retention_id.tax_id.retention_type)
                ],
            }
        return res

    # @api.onchange('actual_payment_retention')
    def onchange_actual_payment_retention(self):
        if self.is_profit_retention():
            self.update({'amount': self.actual_payment_retention})

    def is_profit_retention(self):
        return self.retention_type == 'profit'

    def create_voucher_move_line(self):
        voucher = self.payment_order_id
        self.ensure_one()
        retention = self

        if retention.amount == 0.0:
            return {}

        # Check if the date is already setted
        # if not set the date of the voucher
        retention_vals = {}
        if not retention.date:
            retention_vals['date'] = voucher.date

        company_currency = voucher.company_id.currency_id.id
        current_currency = self.currency_id.id

        tax_amount_in_company_currency = retention.amount
        debit = credit = 0.0

        retention.write(retention_vals)

        debit = credit = 0.0
        if voucher.type in ('purchase', 'payment'):
            credit = tax_amount_in_company_currency
        elif voucher.type in ('sale', 'receipt'):
            debit = tax_amount_in_company_currency
        if debit < 0:
            credit = -debit
            debit = 0.0
        if credit < 0:
            debit = -credit
            credit = 0.0
        sign = debit - credit < 0 and -1 or 1

        if voucher.type == 'payment' and not voucher.disable_retentions:
            self.apply_retention_sequence()

        # Create the move line of the retetention
        move_line = {
            'name': retention.name or '/',
            'debit': debit,
            'credit': credit,
            'account_id': retention.account_id.id,
            'tax_line_id': retention.retention_id.tax_id.id,
            'journal_id': voucher.journal_id.id,
            'partner_id': voucher.partner_id.id,
            'currency_id': company_currency != current_currency
            and current_currency
            or False,
            'amount_currency': company_currency != current_currency
            and sign * retention.amount_currency
            or 0.0,
            'date': voucher.date,
            'date_maturity': voucher.date_due,
        }

        return move_line

    def apply_retention_sequence(self):
        if not self.retention_id.sequence_id:
            raise ValidationError(
                _(
                    "This journal '%s' does not have a sequence.\n"
                    "To add one, go to the journal and create a sequence"
                )
                % self.retention_id.name
            )
        number = self.retention_id.sequence_id._next()
        self.write({'certificate_no': number})

    @api.model
    def get_readeable_name(self):
        """
        Returns an easy name used for exporters to print error messages
        """
        rl_id = self.id
        rl_name = self.name
        rl_partner_name = self.partner_id.name or 'Undefined'
        name = u"RTL(#{})[{}-{}]".format(rl_id, rl_name, rl_partner_name)
        return name


class RetentionMoveLine(models.Model):
    _name = 'retention.move.line'
    _description = 'Retention move lines showed in payment order'

    payment_order_line_id = fields.Many2one(
        comodel_name='account.payment.order.retention.line',
        string='Payment order',
        ondelete='cascade',
    )
    move_id = fields.Many2one(comodel_name='account.move', string='Move')
    move_type = fields.Char(string='Move type', readonly=True)
    move_name = fields.Char(string='Move name', readonly=True)
    total_without_vat = fields.Float(string='Total without vat', readonly=True)
    payment_order_reference = fields.Char(string="Payment order", readonly=True)


class AccountPaymentOrderConceptLine(models.Model):
    _name = "account.payment.order.concept.line"
    _description = "Account Payment Order Concept Line"

    name = fields.Char(string='Description', size=128)
    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Journal',
    )
    account_id = fields.Many2one(
        comodel_name='account.account', string='Account', required=True
    )
    payment_order_id = fields.Many2one(
        comodel_name='account.payment.order',
        string='Voucher',
    )
    amount = fields.Float(
        string='Amount',
        digits='Account',
    )
    account_analytic_id = fields.Many2one(
        comodel_name='account.analytic.account',
        string='Analytic Account',
    )

    @api.onchange('journal_id')
    def change_journal_id(self):
        if self.journal_id:
            self.account_id = self.journal_id.loss_account_id.id

    @api.onchange('account_id')
    def change_account_id(self):
        if self.account_id:
            journal_ids = self.env['account.journal'].search(
                [('loss_account_id', '=', self.account_id.id)]
            )
            self.journal_id = journal_ids and journal_ids[0] or False


class AccountPaymentOrderIssuedCheckLine(models.Model):
    _name = 'account.payment.order.issued.check.line'
    _description = 'Model to communicate issued checks with payment orders'

    payment_order_id = fields.Many2one(comodel_name='account.payment.order')
    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='journal',
        domain=[('type', '=', 'bank')],
    )
    checkbook_id = fields.Many2one(
        comodel_name='account.payment.method.line',
        string='Checkbook',
        required=True,
    )
    issued_check_id = fields.Many2one(
        comodel_name='account.check',
        string='Check',
        required=True,
    )
    bank_id = fields.Many2one(
        comodel_name='res.bank',
        related='issued_check_id.bank_id',
        string='Bank',
    )
    type = fields.Selection(related='issued_check_id.type', string='Type')
    checkbook_format = fields.Selection(
        related='issued_check_id.checkbook_format', string='Format'
    )
    amount = fields.Float(string='Amount', required=True)
    issue_date = fields.Date(string='Issue Date')
    payment_date = fields.Date(
        string='Payment Date',
        help="Only if this check is post dated",
    )
    clearing = fields.Selection(
        selection=[('24', '24 hs'), ('48', '48 hs'), ('72', '72 hs')],
        string='Clearing',
        default='24',
    )
    origin = fields.Char(string='Origin', size=64)
    signatory = fields.Char(string='Signatory', size=64)
    crossed = fields.Boolean(string='Crossed')
    not_order = fields.Boolean(string='Not Order')
    amount_currency = fields.Float(
        related='issued_check_id.amount_currency',
        string='Amount Currency',
    )

    @api.onchange('issue_date')
    def _onchange_issue_date(self):
        if not self.issue_date:
            return
        if self.type == 'common':
            self.payment_date = self.issue_date

    @api.model_create_multi
    def create(self, vals):
        res = super().create(vals)
        for line in res:
            line.issued_check_id.write(self.prepare_line_vals(line))
        return res

    def write(self, vals):
        if vals.get('issued_check_id'):
            self.issued_check_id.write(self.clear_check_vals())
        res = super().write(vals)
        self.issued_check_id.write(self.prepare_line_vals())
        return res

    def unlink(self):
        for line in self:
            if line.issued_check_id.issued_check_state != 'draft':
                raise ValidationError(
                    _("Your are trying to delete a check that is not in draft")
                )
            line.issued_check_id.write(self.clear_check_vals())
        return super().unlink()

    def prepare_line_vals(self, line=False):
        line = line or self
        return {
            'payment_order_id': line.payment_order_id.id,
            'amount': line.amount,
            'issue_date': line.issue_date,
            'payment_date': line.payment_date,
            'clearing': line.clearing,
            'origin': line.origin,
            'signatory': line.signatory,
            'crossed': line.crossed,
            'not_order': line.not_order,
        }

    def clear_check_vals(self):
        return {
            'payment_order_id': False,
            'amount': False,
            'issue_date': False,
            'payment_date': False,
            'clearing': False,
            'origin': False,
            'signatory': False,
            'crossed': False,
            'not_order': False,
        }
