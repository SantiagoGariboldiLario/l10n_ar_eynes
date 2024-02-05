##############################################################################
#   Copyright (c) 2018 Eynes/E-MIPS (www.eynes.com.ar)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
##############################################################################

import json
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class AccountAccount(models.Model):
    _name = 'account.account'
    _inherit = 'account.account'

    perception_concept_ids = fields.Many2many(
        comodel_name='perception.concept',
        relation='account_perception_concept_rel',
        column1='account_id',
        column2='concept_id',
        string='Concepts',
    )


class PerceptionTaxLine(models.Model):
    _name = "perception.tax.line"
    _description = "Perception Tax Line"

    # TODO: Maybe should add states to this object
    # to manage properties depending its state
    name = fields.Char(
        string='Perception',
        required=True,
        size=64,
    )
    date = fields.Date(
        index=True,
    )
    invoice_id = fields.Many2one(
        'account.move',
        string='Invoice',
        ondelete='cascade',
    )
    base = fields.Float(
        digits='Account',
    )
    amount = fields.Float(
        digits='Account',
    )
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
    perception_id = fields.Many2one(
        'account.journal',
        string='Perception Configuration',
        required=True,
        help="Perception configuration used for this perception tax, "
        "where all the configuration resides. Accounts, Tax Codes, etc.",
    )
    perception_id_domain = fields.Char(compute='_compute_perception_id_domain')
    base_amount = fields.Float(
        'Base Code Amount',
        digits='Account',
    )
    tax_amount = fields.Float(
        'Tax Code Amount',
        digits='Account',
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self._default_company_id(),
        readonly=True,
        required=True,
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

    def _default_company_id(self):
        return self.env.company.id

    @api.depends('invoice_id')
    def _compute_perception_id_domain(self):
        for rec in self:
            domain = [
                ('type', '=', 'perceptions'),
                ('company_id', '=', self.env.user.company_id.id),
            ]
            if self.invoice_id:
                if self.invoice_id.move_type.startswith('in_'):
                    domain.append(('tax_id.type_tax_use', '=', 'purchase'))
                else:
                    domain.append(('tax_id.type_tax_use', '=', 'sale'))
            rec.perception_id_domain = json.dumps(domain)

        return domain

    def _compute_base_amount_second_cur(self):
        for rec in self:
            rec.base_secondary_currency = 0
            rec.amount_secondary_currency = 0
            if rec.invoice_id.is_multi_currency:
                currency_rate = rec.invoice_id.currency_rate
                rec.base_secondary_currency = rec.base * currency_rate
                rec.amount_secondary_currency = rec.amount * currency_rate

    @api.onchange('perception_id')
    def _onchange_perception(self):
        res = {}
        if self.perception_id:
            res['domain'] = {
                'concept_id': [
                    ('type', '=', self.perception_id.tax_id.retention_type)
                ],
            }
        self.name = self.perception_id.name
        self.state_id = self.perception_id.state_id.id
        return res

    def compute_all(self, currency=None):
        if len(self) == 0:
            company_id = self.env.user.company_id
        else:
            company_id = self[0].company_id
        if not currency:
            currency = company_id.currency_id
        taxes = []
        taxes.append(
            {
                'id': self.perception_id.tax_id.id,
                'name': self.name,
                'amount': self.amount,
                'base': self.base,
            }
        )

        return taxes

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

    def _compute(self, invoice, base, amount):
        """
        self: perception.tax.line
        invoice: account.invoice
        """
        # Nos fijamos la currency de la invoice
        currency = invoice.currency_id.with_context(
            date=invoice.invoice_date or fields.Date.context_today(invoice)
        )
        company_currency = invoice.company_id.currency_id
        if invoice.type in ('out_invoice', 'in_invoice'):
            base_amount = currency.compute(base, company_currency, round=False)
            tax_amount = currency.compute(amount, company_currency, round=False)
        else:  # invoice is out_refund
            base_amount = currency.compute(
                base * -1, company_currency, round=False
            )
            tax_amount = currency.compute(
                amount * -1, company_currency, round=False
            )
        return (tax_amount, base_amount)


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

    @api.model
    def _get_company(self):
        return self.env.user.company_id

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


class PerceptionActivity(models.Model):
    _name = "perception.activity"
    _description = "Perception Gross Income Activity"

    @api.model
    def _get_company(self):
        return self.env.user.company_id

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


class PerceptionTaxApplication(models.Model):
    _name = "perception.tax.application"

    name = fields.Char('Description', size=128)
    reg_code = fields.Integer('Reg. Code')
    concept_id = fields.Many2one('perception.concept', 'Concept')
    activity_id = fields.Many2one('perception.activity', 'Activity')
    perception_tax_id = fields.Many2one(
        comodel_name='account.tax',
        string='Retention',
    )
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
    type = fields.Selection(
        [
            ('vat', 'VAT'),
            ('gross_income', 'Gross Income'),
            ('profit', 'Profit'),
        ],
        'Type',
        required=True,
    )
    sit_iibb = fields.Many2one(
        comodel_name='iibb.situation', string='Situation of IIBB'
    )

    _sql_constraints = [
        (
            'concept_activity_uniq',
            'unique (concept_id, activity_id, perception_id)',
            'The tuple of Concept, Activity must be unique per Perception !',
        ),
    ]

    @api.model
    def _compute_proportional_vat(
        self, percent, line_vals, tax_application=False
    ):
        vat_tax = {}
        base = 0.0
        tax_application = tax_application or self
        for t in tax_application.vat_tax_ids:
            vat_tax[t.tax_id.id] = t.rate

        if line_vals.get('vat_taxes'):
            for tax_id, vals in line_vals['vat_taxes'].items():
                if tax_id in vat_tax:
                    base += vals['base_amount'] * vat_tax[tax_id]

        amount = round(base * (percent / 100.0), 2)
        return amount

    def compute_base(self, percent, line_vals):
        self.ensure_one()
        tax_application = self

        # TODO: De acuerdo al calculation_base,
        # llamamos a la funcion correspondiente
        if tax_application.calculation_base in (
            'proportional_vat',
            'amount_taxed',
        ):
            base = line_vals['amount_taxed']
        elif tax_application.calculation_base == 'amount_total':
            base = line_vals['amount_total']
        elif tax_application.calculation_base == 'amount_no_taxed':
            base = line_vals['amount_no_taxed']
        elif tax_application.calculation_base == 'amount_untaxed':
            base = line_vals['amount_untaxed']
        # elif tax_application.calculation_base == 'other':
        #     base = self._compute_user_defined_base(
        #         cr, uid, invoice, tax_application.user_defined_base, context)
        else:
            return 0.0, 0.0

        return base

    def apply_perception(self, vals, perception_data):
        percent = perception_data['percent']
        excluded_percent = perception_data['excluded_percent']

        # Si la alicuota que esta en la ficha del partner es negativa,
        # se toma la de la regla que se aplica.
        # Si es 0.0, se toma ese valor, 0.0.
        if percent < 0:
            percent = self.percent

        base = vals['base']
        if base < self.tax_allowance:
            return 0.0, 0.0

        if self.exclude_tax_allowance:
            base -= self.tax_allowance

        # TODO: Testear proportional_vat
        if self.calculation_base == 'proportional_vat':
            amount = self._compute_proportional_vat(percent, vals)
        else:
            amount = round(base * (percent / 100.0), 2)

        # Chequeamos contra el minimo a percibir
        if amount < self.tax_minimum:
            return 0.0, 0.0

        # Si la cantidad de la percepcion es 0.0, tambien lo sera
        # la base, para que de esta manera no se aplique percepcion
        if amount == 0.0:
            base = 0.0

        # Si tenemos excluded_percent, lo aplicamos
        amount *= 1 - excluded_percent

        return base, amount
