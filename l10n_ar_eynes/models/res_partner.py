import logging

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.model
    def _get_retentions_domain(self):
        company = self.env.user.company_id
        return [
            '|',
            ('company_id', '=', False),
            ('company_id', '=', company.id),
        ]

    @api.model
    def _get_perceptions_domain(self):
        company = self.env.user.company_id
        return [
            '|',
            ('company_id', '=', False),
            ('company_id', '=', company.id),
        ]

    retention_activity_id = fields.Many2one(
        comodel_name='retention.activity', string='Activity'
    )
    retention_ids = fields.One2many(
        comodel_name='res.partner.retention',
        inverse_name='partner_id',
        string='Retentions Exceptions',
        domain=lambda self: self._get_retentions_domain(),
        help="Here you have to configure retention exceptions for this "
        + "partner with this Fiscal Position",
    )
    advance_retention_ids = fields.One2many(
        comodel_name='res.partner.advance.retention',
        inverse_name='partner_id',
        domain=lambda self: self._get_retentions_domain(),
        string="Advance Payment Concept",
    )
    document_type_id = fields.Many2one(
        comodel_name='res.document.type', string='Document type'
    )
    dst_cuit_id = fields.Many2one(
        comodel_name='dst.cuit.codes', string='Country CUIT'
    )
    dst_cuit = fields.Boolean(
        string="Enable DST CUIT", related='document_type_id.dst_cuit'
    )
    fcred_transfer = fields.Char(string='SCA/ADC (FCE)?', default='SCA')
    perception_ids = fields.One2many(
        'res.partner.perception',
        'partner_id',
        'Defined Perceptions',
        domain=lambda self: self._get_perceptions_domain(),
        help="Here you have to configure perception exceptions for this "
        "partner with this Fiscal Position",
    )
    nro_insc_iibb = fields.Char('Number of IIBB Registration', size=15)
    door = fields.Char(string="Door", size=3)
    floor = fields.Char(string="Floor", size=3)
    num = fields.Char(string="Number", size=5)
    apartment = fields.Char(string="Apartment", size=4)
    express_id = fields.Many2one("res.partner", string="Express")
    last_update_from_afip = fields.Date()
    gross_income_ids = fields.One2many(
        comodel_name='gross.income',
        inverse_name='partner_id',
        string='Gross Income',
    )

    def parse_afip_values(self, values):

        state = self.env["res.country.state"].search(
            [
                ("name", "ilike", values.provincia),
                ("country_id.code", "=", "AR"),
            ],
            limit=1,
        )

        if values.cat_iva == 1:
            fiscal_position_id = self.env.ref(
                "l10n_ar_eynes.fiscal_position_ri"
            ).id
        elif values.cat_iva == 2:
            fiscal_position_id = self.env.ref(
                "l10n_ar_eynes.fiscal_position_rni"
            ).id
        elif values.cat_iva == 3:
            fiscal_position_id = self.env.ref(
                "l10n_ar_eynes.fiscal_position_nr"
            ).id
        elif values.cat_iva == 4:
            fiscal_position_id = self.env.ref(
                "l10n_ar_eynes.fiscal_position_se"
            ).id
        elif values.cat_iva == 5:
            fiscal_position_id = self.env.ref(
                "l10n_ar_eynes.fiscal_position_cf"
            ).id
        elif values.cat_iva == 6:
            fiscal_position_id = self.env.ref(
                "l10n_ar_eynes.fiscal_position_rem"
            ).id
        elif values.cat_iva == 7:
            fiscal_position_id = self.env.ref(
                "l10n_ar_eynes.fiscal_position_snc"
            ).id
        elif values.cat_iva == 8:
            fiscal_position_id = self.env.ref(
                "l10n_ar_eynes.fiscal_position_pe"
            ).id
        elif values.cat_iva == 9:
            fiscal_position_id = self.env.ref(
                "l10n_ar_eynes.fiscal_position_ce"
            ).id
        elif values.cat_iva == 10:
            fiscal_position_id = self.env.ref(
                "l10n_ar_eynes.fiscal_position_lib"
            ).id
        elif values.cat_iva == 11:
            fiscal_position_id = self.env.ref(
                "l10n_ar_eynes.fiscal_position_ri_ap"
            ).id
        elif values.cat_iva == 12:
            fiscal_position_id = self.env.ref(
                "l10n_ar_eynes.fiscal_position_pce"
            ).id
        elif values.cat_iva == 13:
            fiscal_position_id = self.env.ref(
                "l10n_ar_eynes.fiscal_position_ms"
            ).id
        elif values.cat_iva == 14:
            fiscal_position_id = self.env.ref(
                "l10n_ar_eynes.fiscal_position_pces"
            ).id

        vals = {
            "name": values.denominacion,
            "street": values.direccion,
            "city": values.localidad,
            "zip": values.cod_postal,
            "country_id": self.env.ref("base.ar").id,
            "property_account_position_id": fiscal_position_id or False,
            "state_id": state.id or None,
            "last_update_from_afip": fields.Date.today(),
        }
        return vals

    def _get_ws_conf(self):
        WsPadronConfig = self.env['ws.padron.config']
        ctx = self.env.context.copy()
        ctx['company_id'] = self.env.user.company_id.id
        ws_padron_conf = WsPadronConfig.with_context(**ctx).get_config()
        return ws_padron_conf

    def get_data_from_padron_afip(self):
        self.ensure_one()
        cuit = self.vat
        if not cuit:
            return
        ws_conf = self._get_ws_conf()
        ws = ws_conf.ws_auth()
        try:
            ws.Conectar()
            ws.Consultar(cuit)
        except Exception as e:
            raise UserError(f'ERROR: {ws.ErrMsg}') from e
        values = self.parse_afip_values(ws)
        return values

    def _get_perceptions_to_apply(self, invoice_date):
        # Buscamos las percepciones a aplicar segun la posicion fiscal
        perceptions = {}
        for perc in self.property_account_position_id.perception_ids:
            perception = {
                'perception': perc,
                'activity_id': False,
                'excluded_percent': False,
                'percent': -1.0,
                'ex_date_to': False,
                'ex_date_from': False,
                'sit_iibb': False,
                'from_padron': False,
            }

            perceptions[perc.id] = perception

        # Ahora buscamos a ver si tiene alguna excepcion
        partner_perceptions = {}
        partner_perceptions_for_fiscal_position = self.perception_ids.filtered(
            lambda perception: perception.perception_id.id in perceptions.keys()
        )
        partner_perceptions_for_fiscal_position_period = (
            partner_perceptions_for_fiscal_position.filtered(
                lambda perception: not perception.period
                or (
                    perception.period
                    <= invoice_date
                    <= (
                        (perception.period + relativedelta(months=1))
                        - relativedelta(days=1)
                    )
                )
            )
        )
        difference = partner_perceptions_for_fiscal_position.mapped(
            'perception_id'
        ) - partner_perceptions_for_fiscal_position_period.mapped(
            'perception_id'
        )
        if difference:
            raise UserError(
                _(
                    'The perceptions for this partner must be updated: [%(perceptions_name)s]',
                    perceptions_name=', '.join(
                        [diff.name for diff in difference]
                    ),
                )
            )
        for p_perc in partner_perceptions_for_fiscal_position_period:
            perception = {
                'perception': p_perc.perception_id,
                'activity_id': p_perc.activity_id.id,
                'excluded_percent': p_perc.excluded_percent,
                'percent': p_perc.percent,
                'ex_date_to': p_perc.ex_date_to,
                'ex_date_from': p_perc.ex_date_from,
                'sit_iibb': p_perc.sit_iibb,
                'from_padron': p_perc.from_padron,
            }

            partner_perceptions[p_perc.perception_id.id] = perception

        # Actualizamos el diccionario de retenciones
        perceptions.update(partner_perceptions)
        return perceptions

    @api.constrains('vat', 'document_type_id')
    def check_vat_duplicated(self):
        for partner in self:
            if partner.env.context.get('from_website', False):
                continue
            if not partner.vat:
                continue
            document_type = partner.document_type_id
            to_check = document_type.check_duplicated
            if to_check:
                search_param = [
                    ('vat', '=', partner.vat),
                    ('document_type_id', '=', document_type.id),
                    ('parent_id', '=', False),
                ]
                res = self.search_count(search_param)
                if res > 1:
                    raise ValidationError(
                        _(
                            'There is another partner with same '
                            'VAT Information'
                        )
                    )

    @api.onchange('document_type_id')
    def onchange_document_type(self):
        is_dst_cuit = self.document_type_id.dst_cuit
        if not is_dst_cuit:
            self.dst_cuit_id = False

    def write(self, vals):
        vals = self._parse_vat_string(vals)
        gross_income_ids = vals.get('gross_income_ids', [])
        for rec in gross_income_ids:
            if rec[-1] and not rec[-1].get('type_taxpayer'):
                raise ValidationError(
                    _(
                        "You must complete 'Type of taxpayer' field on Gross income configuration."
                    )
                )
        return super(ResPartner, self).write(vals)

    @api.model
    def create(self, vals):
        vals = self._parse_vat_string(vals)
        if vals.get('gross_income_ids'):
            for rec in vals.get('gross_income_ids'):
                if not rec[-1].get('type_taxpayer'):
                    raise ValidationError(
                        _(
                            "You must complete 'Type of taxpayer' field on Gross income configuration."
                        )
                    )
        return super(ResPartner, self).create(vals)

    def _parse_vat_string(self, vals):
        vat = vals.get('vat')
        if vat:
            vat = vat.replace('.', '').replace('-', '')
            vals['vat'] = vat
        return vals

    @api.constrains('vat', 'country_id', 'document_type_id')
    def check_vat(self):
        """
        Check the VAT number depending of the country.
        """
        for partner in self:
            if not partner.vat:
                continue

            if not partner.document_type_id:
                return True

            if not partner.document_type_id.sudo().verification_required:
                return True

            country = self.env.ref('base.ar')
            vat_number = partner.vat
            if partner.document_type_id == self.sudo().env.ref(
                'l10n_ar_eynes.document_cuit_country'
            ):
                country = partner.country_id
            country_code = country.code.lower()

            if not hasattr(partner, 'check_vat_' + country_code):
                return True
            check = getattr(partner, 'check_vat_' + country_code)
            if not check(vat_number):
                raise ValidationError(
                    _(
                        'The %(doc_type)s does not seems to be correct for %(country)s.',
                        doc_type=partner.document_type_id.sudo().name,
                        country=country.name,
                    )
                )
        return True

    @api.model
    def _commercial_fields(self):
        return super(ResPartner, self)._commercial_fields() + [
            'document_type_id'
        ]

    def check_vat_ar(self, vat):
        """
        Check VAT Routine for Argentina.
        """
        cuit = self.sudo().env.ref('l10n_ar_eynes.document_cuit')
        cuil = self.sudo().env.ref('l10n_ar_eynes.document_cuil')
        dni = self.sudo().env.ref('l10n_ar_eynes.document_dni')
        if self.document_type_id == cuit:
            if len(vat) != 11:
                return False
        if self.document_type_id == cuil:
            if len(vat) != 11:
                return False
        if self.document_type_id == dni:
            if len(vat) > 8:
                return False
        try:
            int(vat)
        except ValueError:
            return False

        check_list = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]

        var1 = 0
        for i in range(10):
            var1 = var1 + int(vat[i]) * check_list[i]
        var3 = 11 - var1 % 11

        if var3 == 11:
            var3 = 0
        if var3 == 10:
            var3 = 9
        if var3 == int(vat[10]):
            return True

        return False

    def _get_retentions_to_apply(self, operation_date):
        # Buscamos las retenciones a aplicar segun la posicion fiscal
        retentions = {}
        for ret in self.property_account_position_id.retention_ids:
            retention = {
                'retention': ret,
                'activity_id': False,
                'excluded_percent': False,
                'percent': -1.0,
                'ex_date_to': False,
                'ex_date_from': False,
                'sit_iibb': False,
                'exclusion_date_certificate': False,
                'from_padron': False,
            }
            retentions[ret.id] = retention

        # Ahora buscamos a ver si tiene alguna excepcion
        partner_retentions = {}
        for p_ret in self.retention_ids:
            excluded_percent = p_ret.excluded_percent
            # ~ ddate = dt.strftime(operation_date, DSDF)
            # ddate = dt.strftime(operation_date, "%Y-%m-%d %H:%M:%S")
            # ~ tzd = fields.Datetime.context_timestamp(self, ddate)
            # Chequeamos que la retencion este en un periodo valido
            if excluded_percent:
                if p_ret.ex_date_from and p_ret.ex_date_to:
                    # Exclusion applies if we are into the boundaries
                    if not (
                        p_ret.ex_date_from <= operation_date <= p_ret.ex_date_to
                    ):
                        excluded_percent = False
                elif p_ret.ex_date_from:
                    # Exclusion applies only if we are latter than date_from
                    if not (p_ret.ex_date_from <= operation_date):
                        excluded_percent = False
                elif p_ret.ex_date_to:
                    # Exclusion applies only if we are before than ex_date_to
                    if not (operation_date <= p_ret.ex_date_to):
                        excluded_percent = False

            retention = {
                'retention': p_ret.retention_id,
                'excluded_percent': excluded_percent,
                'percent': p_ret.percent,
                'ex_date_to': p_ret.ex_date_to,
                'ex_date_from': p_ret.ex_date_from,
                'sit_iibb': p_ret.sit_iibb,
                'exclusion_date_certificate': p_ret.exclusion_date_certificate,
                'from_padron': p_ret.from_padron,
            }

            partner_retentions[p_ret.retention_id.id] = retention

        # Actualizamos el diccionario de retenciones
        retentions.update(partner_retentions)
        return retentions


class ResPartnerRetention(models.Model):
    _name = "res.partner.retention"
    _description = "Retention Defined in Partner"
    _rec_name = 'retention_id'

    partner_id = fields.Many2one(comodel_name='res.partner', string='Partner')
    retention_id = fields.Many2one(
        comodel_name='account.journal',
        string='Retention',
        domain=[('type', '=', 'retentions')],
        required=True,
    )
    percent = fields.Float(
        string='Percent', compute='_compute_retention_percent', store=True
    )
    excluded_percent = fields.Float('Percentage of Exclusion')
    ex_date_from = fields.Date('From date')
    ex_date_to = fields.Date('To date')
    exclusion_certificate = fields.Binary(string='Exclusion Certificate')
    exclusion_date_certificate = fields.Date(
        string='Exclusion General Resolution Date'
    )
    sit_iibb = fields.Many2one(
        comodel_name='iibb.situation', string='Situation of IIBB'
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        related='retention_id.company_id',
        string='Company',
    )
    from_padron = fields.Boolean(string="From Padron")

    # _sql_constraints = [
    #     (
    #         'retention_partner_unique',
    #         'unique(partner_id, retention_id)',
    #         _(
    #             'There must be only one retention of this type configured for the partner'
    #         ),
    #     )
    # ]

    @api.depends(
        'retention_id',
        'partner_id.retention_activity_id',
        'retention_id.tax_id.vat_application_ids',
        'retention_id.tax_id.gi_application_ids',
        'retention_id.tax_id.profit_application_ids',
    )
    def _compute_retention_percent(self):
        for p_retention in self:
            ret_id = p_retention.retention_id
            ret_activity = p_retention.partner_id.retention_activity_id
            ret_tax = ret_id.tax_id
            ret_tax_type = ret_tax.retention_type
            if ret_id and not ret_tax_type:
                raise ValidationError(
                    _(
                        "Please configure retention_type in the "
                        "account.tax [%s]."
                    )
                    % ret_tax.name
                )
            if not p_retention.retention_id or not ret_activity:
                continue

            if ret_tax:
                ret_lines = {
                    'vat': ret_tax.vat_application_ids,
                    'gross_income': ret_tax.gi_application_ids,
                    'profit': ret_tax.profit_application_ids,
                }
                p_retention.percent = (
                    ret_lines[ret_tax_type]
                    .filtered(
                        lambda retline: retline.activity_id == ret_activity
                    )
                    .percent
                )

    @api.constrains('excluded_percent')
    def _check_excluded_percent(self):
        for p_ret in self:
            if not (0 <= p_ret.excluded_percent <= 1):
                raise ValidationError(
                    _(
                        "The Excluded Percent Should be a value "
                        "between 0 and 1"
                    )
                )


class ResPartnerAdvanceRetention(models.Model):
    _name = "res.partner.advance.retention"
    _description = "Retention advanced defined in Partner"

    retention_id = fields.Many2one(
        comodel_name='account.journal',
        string='Retention',
        domain=[('type', '=', 'retentions')],
        required=True,
    )
    concept_id = fields.Many2one(
        comodel_name='retention.concept', string="Concept", required=True
    )
    partner_id = fields.Many2one(comodel_name='res.partner', string="Partner")
    company_id = fields.Many2one(
        comodel_name='res.company',
        related='retention_id.company_id',
        string='Company',
        store=True,
    )


class DstCuitCodes(models.Model):
    _name = "dst.cuit.codes"
    _description = "DST CUIT Codes"
    _order = 'name'

    code = fields.Float('Code', digits=(12, 0), required=True)
    name = fields.Char('Desc', required=True, size=64)
    wsfex_config_id = fields.Many2one('wsfex.config')


class ResPartnerPerception(models.Model):
    _name = "res.partner.perception"
    _description = "Perception Defined in Partner"
    _rec_name = 'perception_id'

    perception_id = fields.Many2one(
        'account.journal',
        'Perception',
        required=True,
        domain=lambda self: [
            ('type', '=', 'perceptions'),
            ('company_id', '=', self.env.user.company_id.id),
        ],
    )
    activity_id = fields.Many2one('perception.activity', 'Activity')
    percent = fields.Float('Percent', required=True)
    excluded_percent = fields.Float('Percentage of Exclusion')
    ex_date_from = fields.Date('From date')
    ex_date_to = fields.Date('To date')
    exclusion_certificate = fields.Binary(string='Exclusion Certificate')
    partner_id = fields.Many2one('res.partner', 'Partner')
    sit_iibb = fields.Many2one(
        comodel_name='iibb.situation', string='Situation of IIBB'
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        related='perception_id.company_id',
        string='Company',
        store=True,
    )
    from_padron = fields.Boolean(string="From Padron")

    # _sql_constraints = [('perception_partner_unique',
    #                      'unique(partner_id, perception_id)',
    #                      'There must be only one perception of this ' +
    #                      'type configured for the partner')]

    @api.onchange('perception_id')
    def perception_id_change(self):
        perception_type = self.perception_id.type
        domain = [('type', '=', perception_type)]
        return {'domain': {'activity_id': domain}}
