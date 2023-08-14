from odoo import _, exceptions, fields, models


class AccountTax(models.Model):
    _inherit = 'account.tax'

    afip_code = fields.Char(string="AFIP Code", size=4)
    check_sit_iibb = fields.Boolean(
        string='Check IIBB Situation',
        default=False,
        help="If checked, when IIBB situation is Multilateral, "
        + "this perception is always applicable",
    )
    is_bank_settlement = fields.Boolean('Is Bank Settlement')
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
    from_register_AGIP = fields.Boolean('From AGIP Register')
    retention_type = fields.Selection(
        selection=[
            ('vat', 'VAT'),
            ('gross_income', 'Gross Income'),
            ('profit', 'Profit'),
            ('other', 'Other'),
        ],
        string='Type',
        help='Retention/Perception type',
    )
    vat_application_ids = fields.One2many(
        comodel_name='retention.tax.application',
        inverse_name='retention_tax_id',
        string='VAT Tax Application',
        domain=[('type', '=', 'vat')],
    )
    profit_application_ids = fields.One2many(
        comodel_name='retention.tax.application',
        inverse_name='retention_tax_id',
        string='Profit Tax Application',
        domain=[('type', '=', 'profit')],
    )
    gi_application_ids = fields.One2many(
        comodel_name='retention.tax.application',
        inverse_name='retention_tax_id',
        string='Gross Income Tax Application',
        domain=[('type', '=', 'gross_income')],
    )
    sequence_to_use = fields.Many2one(
        comodel_name='ir.sequence', string='Sequence to use'
    )
    general_resolution = fields.Char('GR Number', required=False, size=64)
    notes = fields.Text('Notes')
    tax_group_name = fields.Char(
        string='Tax group name', related='tax_group_id.name'
    )
    is_exempt = fields.Boolean(
        string='Exempt',
        default=False,
        help="Check this if this Tax represent Tax Exempts",
    )
    # PERCEPTION FIELDS:
    perc_vat_application_ids = fields.One2many(
        'perception.tax.application',
        'perception_tax_id',
        'VAT Tax Application for Perceptions',
        domain=[('type', '=', 'vat')],
    )
    perc_profit_application_ids = fields.One2many(
        'perception.tax.application',
        'perception_tax_id',
        'Profit Tax Application for Perceptions',
        domain=[('type', '=', 'profit')],
    )
    perc_gi_application_ids = fields.One2many(
        'perception.tax.application',
        'perception_tax_id',
        'Gross Income Tax Application for Perceptions',
        domain=[('type', '=', 'gross_income')],
    )

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
    ):
        res = super(AccountTax, self).compute_all(
            price_unit,
            currency,
            quantity,
            product,
            partner,
            is_refund,
            handle_price_include,
            include_caba_tags,
        )
        for tax in self:
            res_tax_vals = res.get('taxes', [])
            for res_tax in res_tax_vals:
                if tax.id == res_tax['id']:
                    res_tax.update(
                        {
                            'tax_group_name': tax.tax_group_name,
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
            raise exceptions.ValidationError(
                _("No tax repartition lines where found")
            )

        if len(tax_repartition_lines) != 1:
            raise exceptions.ValidationError(
                _("There should only be one repartition line")
            )

        return tax_repartition_lines[0].account_id

    def get_retention_account(self):
        tax_repartition_lines = self.invoice_repartition_line_ids.filtered(
            lambda x: x.repartition_type == 'tax' and x.account_id
        )
        if not tax_repartition_lines:
            raise exceptions.ValidationError(
                _(
                    "No tax repartition lines account where found for '%(ret_name)s'\n"
                    "Add one on Taxes > '%(ret_name)s' > Invoice Repartition Lines",
                    ret_name=self.name,
                )
            )

        if len(tax_repartition_lines) != 1:
            raise exceptions.ValidationError(
                _("There should only be one repartition line for '%s'")
                % self.name
            )
        return tax_repartition_lines[0].account_id
