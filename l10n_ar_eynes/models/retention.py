from odoo import fields, models, api, _
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT as DSDF
from odoo.exceptions import ValidationError
from datetime import datetime
from dateutil.relativedelta import relativedelta as relatived


class RetentionConcept(models.Model):
    _name = "retention.concept"
    _description = "Retention Profit Concepts"

    @api.model
    def _get_company(self):
        return self.env.user.company_id

    name = fields.Char('Description', size=256, required=True)
    code = fields.Char('Code', size=32)
    type = fields.Selection(
        selection=[
            ('vat', 'VAT'),
            ('gross_income', 'Gross Income'),
            ('profit', 'Profit'),
            ('other', 'Other')
        ],
        string='Type',
        required=True
    )
    no_subject = fields.Boolean(
        string='No Subject',
        help="Check this if Retention should not be applied for this Concept"
    )
    account_ids = fields.Many2many(
        comodel_name='account.account',
        relation='account_retention_concept_rel',
        column1='concept_id',
        column2='account_id',
        string='Accounts'
    )
    notes = fields.Text('Notes')
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        default=lambda self: self._get_company(),
        readonly=True,
    )


class RetentionActivity(models.Model):
    _name = "retention.activity"
    _description = "Retention Gross Income Activity"

    @api.model
    def _get_company(self):
        return self.env.user.company_id

    name = fields.Char('Description', size=256, required=True)
    code = fields.Char('Code', size=32)
    type = fields.Selection(
        selection=[
            ('vat', 'VAT'),
            ('gross_income', 'Gross Income'),
            ('profit', 'Profit'),
            ('other', 'Other')
        ],
        string='Type',
        required=True
    )
    notes = fields.Text('Notes')
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        default=lambda self: self._get_company(),
        readonly=True,
    )


class RetentionVatTax(models.Model):
    _name = "retention.vat.tax"
    _description = "VAT Taxes for Retention Calculation"
    _rec_name = 'tax_id'

    tax_id = fields.Many2one('account.tax', 'VAT Tax', required=True)
    application_id = fields.Many2one(
        comodel_name='retention.tax.application',
        string='Application',
        required=True
    )
    rate = fields.Float(
        string='Rate',
        help="Rate from 1.0 to 0.0. This is the proportion of percent "
        + "applied to base amount of this tax."
    )


class RetentionScale(models.Model):
    _name = "retention.scale"
    _description = "Scale for Retention Calculation"

    name = fields.Char('Name', required=True, size=64)
    line_ids = fields.One2many(
        comodel_name='retention.scale.line',
        inverse_name='scale_id',
        string='Scale Lines'
    )


class RetentionScaleLine(models.Model):
    _name = "retention.scale.line"
    _description = "Scale Line for Retention Calculation"

    name = fields.Char('Name', required=True, size=64)
    limit = fields.Float('Limit', required=True)
    percent = fields.Float('Percent', required=True)
    scale_id = fields.Many2one('retention.scale', 'Scale', required=True)


class RetentionTaxApplication(models.Model):
    _name = "retention.tax.application"
    _description = "Retention configuration for activity or concept"

    name = fields.Char('Description', size=128)
    reg_code = fields.Integer('Reg. Code')
    concept_id = fields.Many2one('retention.concept', 'Concept')
    activity_id = fields.Many2one('retention.activity', 'Activity')
    retention_journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Retention',
        domain=[('type', '=', 'retentions')]
    )
    # Minimo No Imponible
    tax_allowance = fields.Float(
        string='Tax Allowance',
        digits='Account',
        help="Retention will be calculated over this amount."
    )
    exclude_tax_allowance = fields.Boolean(
        string='Exclude Tax Allowance',
        default=False,
        help="Check this if Tax Allowance should be excluded "
        + "from calculated Base"
    )
    calculation_base = fields.Selection(
        selection=[
            ('amount_untaxed', 'Invoice Subtotal'),
            # Alicuota proporcional al IVA
            ('proportional_vat', 'Rate Proportional VAT'),
            ('payment_amount_untaxed', 'Payment Amount Untaxed'),
            # ('amount_taxed', 'Invoice Net Taxed'),
            # ('amount_no_taxed', 'Invoice Net Untaxed'),
            # ('amount_total', 'Invoice Total'),
            # ('payment_amount', 'Payment Amount'),
        ],
        string='Calculation Base',
        required=True
    )
    vat_tax_ids = fields.One2many(
        'retention.vat.tax',
        'application_id',
        'VAT Taxes for Calculation'
    )
    # Monto Minimo
    tax_minimum = fields.Float(
        'Tax Minimum',
        digits='Account',
        help="Retention is performed when the amount thereof "
        + "exceeds this value."
    )
    aliq_type = fields.Selection(
        selection=[
            ('percent', 'Percent'),
            ('scale', 'Scale')
        ],
        string='Aliquot Type',
        required=True
    )
    percent = fields.Float(
        'Percent', digits='Account',
        help="Percent to Apply if the Partner is inscripted in the Tax"
    )
    scale_id = fields.Many2one('retention.scale', 'Scale')
    type = fields.Selection(
        selection=[
            ('vat', 'VAT'),
            ('gross_income', 'Gross Income'),
            ('profit', 'Profit')
        ],
        string='Type',
        required=True
    )
    sit_iibb = fields.Selection(
        selection=[
            ('1', 'Local'),
            ('2', 'Convenio Multilateral'),
            ('4', 'No Inscripto'),
            ('5', 'Regimen Simplificado')
        ],
        string='Situation of IIBB'
    )

    _sql_constraints = [
        ('concept_activity_uniq',
         'unique (concept_id, activity_id, retention_id)',
         'The tuple of Concept, Activity must be unique per Retention !'),
    ]

    def _compute_proportional_vat(self, percent, line_vals):
        vat_tax = {}
        base = 0.0

        for t in self.vat_tax_ids:
            vat_tax[t.tax_id.id] = t.rate

        for tax_id, vals in line_vals['vat_taxes'].iteritems():
            if tax_id in vat_tax:
                base += vals['base_amount'] * vat_tax[tax_id]

        amount = round(base * (percent / 100.0), 2)
        return amount

    def _compute_amount_via_scale(self, base):

        amount = 0.0
        prev_limit = 0.0

        for sc in self.scale_id.line_ids:
            range_limit = sc.limit - prev_limit
            b = base - sc.limit

            if b < 0 or sc.limit == -1:
                b = base - prev_limit
                amount += round(b * (sc.percent / 100.0), 2)
                return amount
            else:
                amount += round((range_limit) * (sc.percent / 100.0), 2)

            prev_limit = sc.limit

        return amount

    def _get_month_date_span_from_date(self, date=False):
        if not date:
            date = fields.Date.context_today(self)

        # Obtenemos las fechas de mes calendario
        # al que corresponde este voucher

        # dt = datetime.strptime(date, DSDF)
        dt = datetime.strptime(str(date), DSDF)
        date_start = (dt + relatived(day=1)).strftime(DSDF)
        date_finish = (dt + relatived(day=31)).strftime(DSDF)
        return date_start, date_finish

    def get_period_partner_payments(self, partner, concept, po_date=False):

        date_start, date_finish = self._get_month_date_span_from_date(po_date)
        payment_order_model = self.env['account.payment.order']
        payment_order_line_model = self.env['account.payment.order.line']
        prev_pos = payment_order_model.search([
            ('partner_id', '=', partner.id),
            ('state', '=', 'posted'),
            ('date', '>=', date_start),
            ('date', '<=', date_finish)
        ])
        debt_moves = prev_pos.mapped('debt_line_ids.move_line_id.move_id')
        debt_untax_mls = debt_moves.mapped('line_ids').filtered(
            lambda ml: ml.account_id in concept.account_ids
            and ml.tax_ids and not ml.tax_line_id)
        income_moves = prev_pos.mapped('income_line_ids.move_line_id.move_id')
        income_untax_mls = income_moves.mapped('line_ids').filtered(
            lambda ml: ml.account_id in concept.account_ids
            and ml.tax_ids and not ml.tax_line_id)
        # Use the proportional amount of line being paid, searching in
        # the old apo's and gathering the apol related to the untaxed ones
        debt_untax_mls_ok = []
        for ml in debt_untax_mls:
            amls_w_tax = ml.move_id.mapped('line_ids').filtered(
                lambda ml: ml.account_id.internal_type in ['payable']
            )
            domain = [
                ('payment_order_id', 'in', prev_pos.ids),
                ('move_line_id', 'in', amls_w_tax.ids),
            ]
            pol_todo = payment_order_line_model.search(domain)
            amount = (ml.credit or ml.debit)
            factor = 0.0
            for pol in pol_todo:
                factor += pol.amount / pol.amount_original

            if factor:
                amount = amount * round(factor, 3)
#            if pol_todo:
#                factor = pol_todo.amount / pol_todo.amount_original
#                amount = amount * factor
            debt_untax_mls_ok.append(amount)
        # Use the proportional amount of line being paid, searching in
        # the old apo's and gathering the apol related to the untaxed ones
        income_untax_mls_ok = []
        for ml in income_untax_mls:
            amls_w_tax = ml.move_id.mapped('line_ids').filtered(
                lambda ml: ml.account_id.internal_type in ['payable']
            )
            domain = [
                ('payment_order_id', 'in', prev_pos.ids),
                ('move_line_id', 'in', amls_w_tax.ids),
            ]
            pol_todo = payment_order_line_model.search(domain)
            amount = (ml.credit or ml.debit)
            factor = 0.0
            for pol in pol_todo:
                factor += pol.amount / pol.amount_original

            if factor:
                amount = amount * round(factor, 3)
            income_untax_mls_ok.append(amount)
        untaxed_debt = sum(debt_untax_mls_ok)
        untaxed_inc = sum(income_untax_mls_ok)
        untaxed_amount = untaxed_debt - untaxed_inc
        untaxed_amount += self.get_period_partner_advance_payments(prev_pos)
        return untaxed_amount

    def get_period_partner_advance_payments(self, prev_pos):
        extra_untaxed_amount = 0.0
        for po in prev_pos:
            if any(po.debt_line_ids.mapped('amount')
                   + po.income_line_ids.mapped('amount')) or not po.amount \
                    or not po.retention_ids:
                continue
            extra_untaxed_amount += po.amount - sum(
                po.retention_ids.mapped('amount'))
        return extra_untaxed_amount

    def get_period_base_amount(self, partner, concept, po_date=False):
        retention_line_model = self.env['retention.tax.line']

        date_start, date_finish = self._get_month_date_span_from_date(po_date)

        # Buscamos las retenciones
        domain = [
            ('partner_id', '=', partner.id),
            ('retention_id.type', '=', 'profit'),
            ('concept_id', '=', concept.id),
            ('date', '>=', date_start),
            ('date', '<=', date_finish),
            ('payment_order_id.state', 'in', ['posted']),
        ]

        ret_lines = retention_line_model.search(
            domain, order="date desc, id desc")

        base = sum([ret.base for ret in ret_lines])
        amount = sum([ret.amount for ret in ret_lines])
        return base, amount

    def apply_retention(self, partner, percent, excluded_percent,
                        vals, po_date):
        # Si la alicuota que esta en la ficha del partner es negativa,
        # se toma la de la regla que se aplica.
        # Si es 0.0, se toma ese valor, 0.0.
        if percent < 0:
            percent = self.percent

        # Aca tenemos que ver que si es un calculo de ganancias hay que
        # chequear el tema de varios pagos en un mes al mismo beneficiario
        period_base = 0.0
        period_amount = 0.0
        period_payment_amount = 0.0
        base = vals['base']
        to_pay = vals['to_pay']
        if self.calculation_base in [
                'payment_amount', 'payment_amount_untaxed']:
            base = to_pay

        if self.retention_id.type == 'profit':
            period_base, period_amount = self.get_period_base_amount(
                partner, self.concept_id, po_date)
            period_payment_amount = self.get_period_partner_payments(
                partner, self.concept_id, po_date)

            # Si tenemos pagos anteriores de este concepto,
            # los sumamos a la base y al ser de ganancias,
            # tenemos que usar la cantidad a pagar neto de Impuestos
            base = to_pay + period_payment_amount

        # Puede darse el caso en que FAC-NC quede en 0.0 y
        # realizaba una division por cero
        if round(base, 2) == 0.0:
            return 0.0, 0.0

        # Agregamos el signo de la base si es que viene de una NC
        sign_base = base / abs(base)
        base = abs(base)

        if base < self.tax_allowance:
            return 0.0, 0.0

        if self.exclude_tax_allowance:
            base -= self.tax_allowance

        if self.calculation_base == 'proportional_vat':
            # TODO: Chequear que esta funcion funcione correctamente
            amount = self._compute_proportional_vat(percent, base)
        else:
            if self.aliq_type == 'percent':
                amount = round(base * (percent / 100.0), 2)
            else:
                amount = self._compute_amount_via_scale(base)

        # Si es de ganancias, le detraemos las retenciones de ganancias
        # ya practicadas para este concepto
        # en el mes calendario en pagos previos a este proveedor
        if self.retention_id.type == 'profit':
            amount -= period_amount

        # Chequeamos contra el minimo a percibir
        if amount < self.tax_minimum:
            return 0.0, 0.0

        # Chequeamos que la cantidad a retener no sea negativa
        if amount < 0:
            raise ValidationError(
                _('Retention Error!\n')
                + _('There is an error in retention configuration because '
                    + 'amount of %s is negative') % self.retention_id.name)
        elif amount == 0.0:
            return 0.0, 0.0

        # Aplicamos el porcentaje de eximision si es que lo hay
        amount *= (1 - excluded_percent)

        return base * sign_base, amount * sign_base
