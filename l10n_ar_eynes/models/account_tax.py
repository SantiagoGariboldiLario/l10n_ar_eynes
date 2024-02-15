import logging

from odoo import _, api, exceptions, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.safe_eval import safe_eval, wrap_module

_logger = logging.getLogger(__name__)


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
    apply_custom_code = fields.Boolean(default=False)
    python_code = fields.Text(
        string='Python Code',
        default=(
            "# Enter Python code here. Help about Python expression "
            "is available in the help tab of this document."
        ),
        help="The code will be executed to evaluate "
        "if it is appropriate to apply perception",
    )

    @api.constrains('python_code')
    def _check_syntax_python_code(self):
        for reg in self:
            # if reg.type != 'gross_income':
            #     continue
            try:
                safe_eval(
                    reg.python_code.strip(),
                    {},
                    mode="exec",
                    nocopy=True,
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

    def _get_taxapps_from_code(self, perc_data, invoice=None, po_line=None):
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
        eval_context = self._get_eval_code_context()
        partner = None
        if invoice:
            partner = invoice.partner_id
        if po_line:
            partner = po_line.partner_id

        # Pasamos el parent partner como variable en caso de
        # que exista para poder tomar sus percepciones
        if not partner.is_company and partner.parent_id:
            partner = partner.parent_id

        eval_context.update(
            {
                'perc_data': perc_data,
                'invoice': invoice,
                'partner': partner,
                'perception': self,
                'retention': self,
                'po_line': po_line,
                'invoice_line': po_line.move_line_id if po_line else None,
            }
        )

        try:
            safe_eval(
                self.python_code.strip(),
                eval_context,
                mode="exec",
                nocopy=True,
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
