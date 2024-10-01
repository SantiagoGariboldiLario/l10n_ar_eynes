##############################################################################
#   Copyright (c) 2018 Eynes/E-MIPS (www.eynes.com.ar)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
##############################################################################

import logging

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_is_zero

_logger = logging.getLogger(__name__)


class PerceptionTaxLine(models.Model):
    _name = "perception.tax.line"
    _description = "Perception Tax Line"

    name = fields.Char(
        string='Perception',
        required=True,
        size=64,
        compute='_compute_name',
        store=True,
        copy=True,
    )
    date = fields.Date(index=True, required=True)
    invoice_id = fields.Many2one(
        'account.move', string='Invoice', ondelete='cascade'
    )
    base = fields.Float(digits='Account', required=True)
    amount = fields.Float(digits='Account', required=True)
    base_secondary_currency = fields.Float(
        string='Base in secondary currency',
        digits='Account',
        compute='_compute_base_amount_second_cur',
    )
    amount_secondary_currency = fields.Float(
        string='Amount in secondary currency',
        digits='Account',
        compute='_compute_base_amount_second_cur',
    )
    perception_id_domain = fields.Binary(
        compute='_compute_perception_id_domain'
    )
    perception_id = fields.Many2one(
        'account.tax',
        string='Perception Tax',
        required=True,
        help="Perception configuration used for this perception tax, "
        "where all the configuration resides. Accounts, Tax Codes, etc.",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self._default_company_id(),
        readonly=True,
        required=True,
        store=True,
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Partner',
        required=True,
    )
    vat = fields.Char(
        related='partner_id.vat',
        string='CIF/NIF',
        readonly=True,
    )
    state_id = fields.Many2one(
        'res.country.state',
        string="State/Province",
        related='perception_id.state_id',
        store=True,
    )
    aml_id = fields.Many2one(
        'account.move.line',
        string='Invoice Tax',
        ondelete='cascade',
    )
    manual = fields.Boolean(default=True)
    reg_code = fields.Integer('Reg. Code')
    tax_app_id = fields.Many2one(
        'perception.tax.application', 'Tax Application'
    )
    concept_id = fields.Many2one('perception.concept', 'Concept')

    @api.constrains('base')
    def _check_base_not_zero(self):
        for rec in self:
            if float_is_zero(
                rec.base, precision_rounding=rec.invoice_id.currency_id.rounding
            ):
                raise ValidationError(_("Perception Base can't be zero"))

    @api.constrains('amount')
    def _check_amount_not_zero(self):
        for rec in self:
            if float_is_zero(
                rec.amount,
                precision_rounding=rec.invoice_id.currency_id.rounding,
            ):
                raise ValidationError(_("Perception Amount can't be zero"))

    def _default_company_id(self):
        return self.env.company.id

    @api.depends('perception_id')
    def _compute_name(self):
        for rec in self:
            rec.name = '' if not rec.perception_id else rec.perception_id.name

    @api.depends('invoice_id')
    def _compute_perception_id_domain(self):
        for rec in self:
            domain = [
                ('tax_group_id.group_type', '=', 'perception'),
                ('company_id', '=', rec.env.company.id),
            ]
            if rec.invoice_id:
                if rec.invoice_id.move_type.startswith('in_'):
                    domain.append(('type_tax_use', '=', 'purchase'))
                else:
                    domain.append(('type_tax_use', '=', 'sale'))
            rec.perception_id_domain = domain

    def _compute_base_amount_second_cur(self):
        for rec in self:
            rec.base_secondary_currency = 0
            rec.amount_secondary_currency = 0
            if rec.invoice_id.is_multi_currency:
                currency_rate = rec.invoice_id.currency_rate
                rec.base_secondary_currency = rec.base * currency_rate
                rec.amount_secondary_currency = rec.amount * currency_rate

    # @api.onchange('perception_id')
    # def _onchange_perception(self):
    #     res = {}
    #     if self.perception_id:
    #         res['domain'] = {
    #             'concept_id': [
    #                 ('type', '=', self.perception_id.tax_id.retention_type)
    #             ],
    #         }
    #     self.name = self.perception_id.name
    #     self.state_id = self.perception_id.state_id.id
    #     return res

    # def compute_all(self, currency=None):
    #     if len(self) == 0:
    #         company_id = self.env.user.company_id
    #     else:
    #         company_id = self[0].company_id
    #     if not currency:
    #         currency = company_id.currency_id
    #     taxes = []
    #     taxes.append(
    #         {
    #             'id': self.perception_id.tax_id.id,
    #             'name': self.name,
    #             'amount': self.amount,
    #             'base': self.base,
    #         }
    #     )

    #     return taxes

    @api.model
    def get_readeable_name(self):
        """
        Returns an easy name used for exporters to print error messages
        """
        ptl_id = self.id
        ptl_name = self.name
        ptl_partner_name = self.partner_id.name or 'Undefined'
        name = u"RTL(#{})[{}-{}]".format(ptl_id, ptl_name, ptl_partner_name)
        return name

    # def _compute(self, invoice, base, amount):
    #     """
    #     self: perception.tax.line
    #     invoice: account.invoice
    #     """
    #     # Nos fijamos la currency de la invoice
    #     currency = invoice.currency_id.with_context(
    #         date=invoice.invoice_date or fields.Date.context_today(invoice)
    #     )
    #     company_currency = invoice.company_id.currency_id
    #     if invoice.type in ('out_invoice', 'in_invoice'):
    #         base_amount = currency.compute(base, company_currency, round=False)
    #         tax_amount = currency.compute(amount, company_currency, round=False)
    #     else:  # invoice is out_refund
    #         base_amount = currency.compute(
    #             base * -1, company_currency, round=False
    #         )
    #         tax_amount = currency.compute(
    #             amount * -1, company_currency, round=False
    #         )
    #     return (tax_amount, base_amount)


class PerceptionVatTax(models.Model):
    _name = "perception.vat.tax"
    _description = "VAT Taxes for Perception Calculation"
    _rec_name = 'tax_id'

    tax_id = fields.Many2one('account.tax', 'VAT Tax', required=True)
    application_id = fields.Many2one(
        'perception.tax.application',
        'Perception Tax Application',
        required=True,
    )
    rate = fields.Float(
        'Rate',
        help="Rate from 1.0 to 0.0. This is the proportion of percent "
        "applied to base amount of this tax.",
    )


class PerceptionConcept(models.Model):
    _name = "perception.concept"
    _description = "Perception Concepts"

    name = fields.Char('Description', size=256, required=True)
    code = fields.Char('Code', size=32)
    type = fields.Selection(
        [
            ('vat', 'VAT'),
            ('gross_income', 'Gross Income'),
            ('profit', 'Profit'),
            ('other', 'Other'),
        ],
        'Type',
        required=True,
    )
    no_subject = fields.Boolean(
        'No Subject',
        help="Check this if Perception should not "
        "be applied for this Concept",
    )
    account_ids = fields.Many2many(
        'account.account',
        'account_perception_concept_rel',
        'concept_id',
        'account_id',
        'Accounts',
    )
    notes = fields.Text('Notes')
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        default=lambda self: self._get_company(),
        readonly=True,
    )

    @api.model
    def _get_company(self):
        return self.env.company


class PerceptionActivity(models.Model):
    _name = "perception.activity"
    _description = "Perception Gross Income Activity"

    name = fields.Char('Description', size=256, required=True)
    code = fields.Char('Code', size=32)
    type = fields.Selection(
        [
            ('vat', 'VAT'),
            ('gross_income', 'Gross Income'),
            ('profit', 'Profit'),
            ('other', 'Other'),
        ],
        'Type',
        required=True,
    )
    notes = fields.Text('Notes')
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        default=lambda self: self._get_company(),
        readonly=True,
    )

    @api.model
    def _get_company(self):
        return self.env.company


class PerceptionTaxApplication(models.Model):
    _name = "perception.tax.application"

    name = fields.Char('Description', size=128)
    reg_code = fields.Integer('Reg. Code')
    concept_id_domain = fields.Binary(
        string='Concept filter ', compute='_compute_concept_domain'
    )
    concept_id = fields.Many2one('perception.concept')
    activity_id_domain = fields.Binary(
        string='Activity filter ', compute='_compute_activity_domain'
    )
    activity_id = fields.Many2one('perception.activity')
    perception_tax_id = fields.Many2one(comodel_name='account.tax')
    # Minimo No Imponible
    tax_allowance = fields.Float(
        'Tax Allowance',
        digits='Account',
        help="Perception will be calculated over this amount.",
    )
    exclude_tax_allowance = fields.Boolean(
        'Exclude Tax Allowance',
        default=False,
        help="Check this if Tax Allowance should be excluded from "
        "calculated Base",
    )
    calculation_base = fields.Selection(
        [
            ('amount_taxed', 'Invoice Net Taxed'),
            ('amount_no_taxed', 'Invoice Net Untaxed'),
            ('amount_total', 'Invoice Total'),
            ('amount_untaxed', 'Invoice Subtotal'),
            ('proportional_vat', 'Rate Proportional VAT')
            # Alicuota proporcional al IVA
        ],
        'Calculation Base',
        required=True,
    )
    vat_tax_ids = fields.One2many(
        'perception.vat.tax', 'application_id', 'VAT Taxes for Calculation'
    )
    # Monto Minimo
    tax_minimum = fields.Float(
        'Tax Minimum',
        digits='Account',
        help="Perception is performed when the amount thereof "
        "exceeds this value.",
    )
    percent = fields.Float(
        'Percent',
        digits='Account',
        help="Percent to Apply if the Partner is inscripted in the Tax",
    )
    sit_iibb = fields.Many2one(
        comodel_name='iibb.situation', string='Situation of IIBB'
    )

    _sql_constraints = [
        (
            'concept_activity_uniq',
            'unique (concept_id, activity_id, perception_tax_id)',
            'The tuple of Concept, Activity must be unique per Perception !',
        ),
    ]

    @api.depends('perception_tax_id')
    def _compute_concept_domain(self):
        for rec in self:
            if rec.perception_tax_id:
                rec.concept_id_domain = [
                    ('type', '=', rec.perception_tax_id.retention_type)
                ]
            else:
                rec.concept_id_domain = [()]

    @api.depends('perception_tax_id')
    def _compute_activity_domain(self):
        for rec in self:
            if rec.perception_tax_id:
                rec.activity_id_domain = [
                    ('type', '=', rec.perception_tax_id.retention_type)
                ]
            else:
                rec.activity_id_domain = [()]

    # @api.model
    # def _compute_proportional_vat(
    #     self, percent, line_vals, tax_application=False
    # ):
    #     vat_tax = {}
    #     base = 0.0
    #     tax_application = tax_application or self
    #     for t in tax_application.vat_tax_ids:
    #         vat_tax[t.tax_id.id] = t.rate

    #     if line_vals.get('vat_taxes'):
    #         for tax_id, vals in line_vals['vat_taxes'].items():
    #             if tax_id in vat_tax:
    #                 base += vals['base_amount'] * vat_tax[tax_id]

    #     amount = round(base * (percent / 100.0), 2)
    #     return amount

    def check_applicable(
        self,
        destination_shipping,
        source_shipping,
        sit_iibb=False,
        from_padron=False,
        excluded_percent=0.0,
    ):
        """
        Este método es utilizado para determinar si una percepción debe ser aplicada al cliente
        según su configuración.
        """
        self.ensure_one()

        if not self.perception_tax_id.active:
            return False

        if excluded_percent == 1.0:
            return False

        if not self.perception_tax_id.state_id:
            return True

        if self.perception_tax_id.applicable_state == 'always':
            return True

        if self.perception_tax_id.always_apply_padron and from_padron:
            return True

        # Chequeamos la situacion de IIBB, si es CM,
        # directamente retornamos True
        if self.perception_tax_id.check_sit_iibb:
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
        retention_state = self.perception_tax_id.state_id.id
        destination_shipping = self.env['res.partner'].browse(
            destination_shipping.address_get(['delivery']).get('delivery')
        )
        if self.perception_tax_id.applicable_state == 'dest':
            partner_state = destination_shipping.state_id.id
            if not partner_state:
                raise UserError(
                    _(
                        'There is no State/Province configured for '
                        f'the Supplier while computing {self.name}'
                    )
                )
        elif self.perception_tax_id.applicable_state == 'source':
            partner_state = source_shipping.state_id.id
            if not partner_state:
                raise UserError(
                    _('There is no State/Province configured for this Company')
                )
        # Hacemos el chequeo de los states
        return retention_state == partner_state

    def check_concept(self, account_id):
        """
        Este método es útil cuando ya sabemos que la factura lleva percepciones pero necesitamos chequear si
         un producto en particular está afectado o no.
        """
        if self.concept_id.account_ids.filtered(
            lambda account: account == account_id
        ):
            return True
        return False

    def get_perception_data(self, partner, invoice_date):
        perception = self.perception_tax_id
        # Partimos de la configuración básica de la aplicación de la percepción
        data = {
            'activity_id': self.activity_id.id,
            'excluded_percent': 0.0,
            'percent': self.percent,
            'ex_date_to': False,
            'ex_date_from': False,
            'sit_iibb': False,
            'from_padron': False,
        }

        # Aplicamos la modificación de alícuotas, exclusiones, etc según los datos del padrón:
        invoice_date = invoice_date or fields.Date.today()
        partner_perception_lines = partner.perception_ids.filtered(
            lambda line: line.perception_id == perception
        )
        if self.activity_id:
            partner_perception_lines.filtered(
                lambda line: not line.activity_id
                or line.activity_id == self.activity_id
            )
        partner_perception_period = partner_perception_lines.filtered(
            lambda line: not line.period
            or (
                line.period
                <= invoice_date
                <= (
                    (line.period + relativedelta(months=1))
                    - relativedelta(days=1)
                )
            )
        )
        if not partner_perception_period and partner_perception_lines:
            partner_perception_periods = partner_perception_lines.filtered(
                lambda line: not line.period or (line.period <= invoice_date)
            )
            max_period = max(partner_perception_periods.mapped('period'))
            partner_perception_period = partner_perception_periods.filtered(
                lambda line: line.period == max_period
            )
        if partner_perception_period:
            data.update(
                {
                    'excluded_percent': partner_perception_period.excluded_percent,
                    'percent': partner_perception_period.percent,
                    'ex_date_to': partner_perception_period.ex_date_to,
                    'ex_date_from': partner_perception_period.ex_date_from,
                    'sit_iibb': partner_perception_period.sit_iibb,
                    'from_padron': partner_perception_period.from_padron,
                }
            )

        return data

    def _get_base_from_account_move_lines(self, field, lines):
        return sum(lines.mapped(field))

    def _get_base_from_list(self, field, lines):
        return sum(line[field] for line in lines)

    def compute_base(self, lines):
        self.ensure_one()

        method_name = '_get_base_from_account_move_lines'
        if isinstance(lines, list):
            method_name = '_get_base_from_list'
        method = getattr(self, method_name)

        base = 0.0
        if self.calculation_base in ('proportional_vat', 'amount_taxed'):
            # TODO
            base = method('amount_taxed', lines)
        elif self.calculation_base == 'amount_total':
            base = method('price_total', lines)
        elif self.calculation_base == 'amount_no_taxed':
            # TODO
            base = method('amount_no_taxed', lines)
        elif self.calculation_base == 'amount_untaxed':
            base = method('price_subtotal', lines)

        # Necesitamos cambiarle el signo a la base para el caso de las NC desde POS
        sign = -1 if base < 0 else 1
        base = base * sign
        if base < self.tax_allowance:
            return 0.0

        if self.exclude_tax_allowance:
            base -= self.tax_allowance
        return base * sign

    def apply_perception(self, perception_data):
        percent = perception_data['percent']
        excluded_percent = perception_data['excluded_percent']

        base = self.compute_base(perception_data['lines'])
        if base == 0.0:
            return 0.0, 0.0
        sign = -1 if base < 0 else 1
        base = base * sign
        # # TODO: Testear proportional_vat
        # if self.calculation_base == 'proportional_vat':
        #     amount = self._compute_proportional_vat(percent, vals)
        # else:
        #     amount = round(base * (percent / 100.0), 2)

        amount = base * percent / 100.0
        # Con la presentación de AGIP tuvimos problemas de redondeo. Cuando el importe a percibir
        # era xx.xx5 round() redondeaba para arriba y necesitábamos que redondee para abajo.
        # Explicación en --> https://stackoverflow.com/a/38239630
        amount = round(amount + 10 ** (-len(str(amount)) - 1), 2)

        # Chequeamos contra el minimo a percibir
        if amount < self.tax_minimum:
            return 0.0, 0.0

        # Si la cantidad de la percepcion es 0.0, tambien lo sera
        # la base, para que de esta manera no se aplique percepcion
        if amount == 0.0:
            base = 0.0

        # Si tenemos excluded_percent, lo aplicamos
        amount *= 1 - excluded_percent

        return base * sign, amount * sign
