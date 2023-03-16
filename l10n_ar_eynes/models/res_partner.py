# from datetime import datetime as dt

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError


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

    retention_activity_id = fields.Many2one(
        comodel_name='retention.activity',
        string='Activity'
    )
    retention_ids = fields.One2many(
        comodel_name='res.partner.retention',
        inverse_name='partner_id',
        string='Retentions Exceptions',
        domain=lambda self: self._get_retentions_domain(),
        help="Here you have to configure retention exceptions for this "
        + "partner with this Fiscal Position"
    )
    advance_retention_ids = fields.One2many(
        comodel_name='res.partner.advance.retention',
        inverse_name='partner_id',
        domain=lambda self: self._get_retentions_domain(),
        string="Advance Payment Concept"
    )
    document_type_id = fields.Many2one(
        comodel_name='res.document.type',
        string='Document type'
    )
    dst_cuit_id = fields.Many2one(
        comodel_name='dst.cuit.codes',
        string='Country CUIT'
    )
    dst_cuit = fields.Boolean(
        string="Enable DST CUIT",
        related='document_type_id.dst_cuit'
    )

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
                    ('parent_id', '=', False)
                ]
                res = self.search_count(search_param)
                if res > 1:
                    raise ValidationError(_(
                        'There is another partner with same '
                        'VAT Information'
                    ))

    @api.onchange('document_type_id')
    def onchange_document_type(self):
        is_dst_cuit = self.document_type_id.dst_cuit
        if not is_dst_cuit:
            self.dst_cuit_id = False

    def write(self, vals):
        self.check_vat_string(vals, write=True)
        res = super().write(vals)
        return res

    @api.model
    def create(self, vals_list):
        self.check_vat_string(vals_list)
        return super(ResPartner, self).create(vals_list)

    def check_vat_string(self, vals, write=False):
        vat = vals.get("vat")
        if not vat:
            return False
        ci_extranjera = self.env.ref('l10n_ar_eynes.document_ci_extranjera')
        pasaporte = self.env.ref('l10n_ar_eynes.document_pasaporte')
        if write:
            if [x for x in self if x.document_type_id not in [
                    ci_extranjera, pasaporte]]:
                vat = vat.replace('.', '').replace('-', '')
                if not vat.isdigit():
                    raise ValidationError(_(
                        'The Vat only supports numbers.'
                    ))
                vals['vat'] = vat
        else:
            if vals.get('document_type_id') not in [ci_extranjera, pasaporte]:
                vat = vat.replace('.', '').replace('-', '')
                if not vat.isdigit():
                    raise ValidationError(_(
                        'The Vat only supports numbers.'
                    ))
                vals['vat'] = vat
        return False

    @api.constrains('vat', 'country_id', 'document_type_id')
    def check_vat(self):
        """
        Check the VAT number depending of the country.
        """
        for partner in self:
            if not partner.vat:
                continue
            if partner.country_id:
                vat_country = partner.country_id.code.lower()
                vat_number = partner.vat
            else:
                try:
                    int(partner.vat[:2].lower())
                    vat_country = 'ar'
                    vat_number = partner.vat
                except ValueError:
                    vat_country, vat_number = partner.vat[:2].lower(), \
                        partner.vat[2:].replace(' ', '')
            if not partner.document_type_id:
                return True
            if partner.document_type_id and \
                    not partner.document_type_id.sudo().verification_required:
                return True
            if not hasattr(partner, 'check_vat_' + vat_country):
                return True
            check = getattr(partner, 'check_vat_' + vat_country)
            if not check(vat_number):
                raise ValidationError(_(
                    'The Vat does not seems to be correct.'
                ))
        return True

    @api.model
    def _commercial_fields(self):
        return super(ResPartner, self)._commercial_fields() + \
            ['document_type_id']

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
                    if not (p_ret.ex_date_from <= operation_date <= p_ret.ex_date_to):
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


class resPartnerRetention(models.Model):
    _name = "res.partner.retention"
    _description = "Retention Defined in Partner"
    _rec_name = 'retention_id'

    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Partner'
    )
    retention_id = fields.Many2one(
        comodel_name='account.journal',
        string='Retention',
        domain=[('type', '=', 'retentions')],
        required=True
    )
    percent = fields.Float(
        string='Percent',
        compute='_compute_retention_percent',
        store=True
    )
    excluded_percent = fields.Float('Percentage of Exclusion')
    ex_date_from = fields.Date('From date')
    ex_date_to = fields.Date('To date')
    exclusion_certificate = fields.Binary(string='Exclusion Certificate')
    exclusion_date_certificate = fields.Date(
        string='Exclusion General Resolution Date'
    )
    sit_iibb = fields.Many2one(
        comodel_name='iibb.situation',
        string='Situation of IIBB'
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        related='retention_id.company_id',
        string='Company'
    )
    from_padron = fields.Boolean(string="From Padron")

    _sql_constraints = [
        (
            'retention_partner_unique',
            'unique(partner_id, retention_id)',
            _('There must be only one retention of this type configured for the partner')
        )
    ]

    @api.depends('retention_id',
                 'partner_id.retention_activity_id',
                 'retention_id.tax_id.vat_application_ids',
                 'retention_id.tax_id.gi_application_ids',
                 'retention_id.tax_id.profit_application_ids')
    def _compute_retention_percent(self):
        for p_retention in self:

            ret_activity = p_retention.partner_id.retention_activity_id
            if not p_retention.retention_id or not ret_activity:
                continue
            ret_tax = p_retention.retention_id.tax_id
            ret_lines = {
                'vat': ret_tax.vat_application_ids,
                'gross_income': ret_tax.gi_application_ids,
                'profit': ret_tax.profit_application_ids,
            }
            p_retention.percent = ret_lines[ret_tax.retention_type].filtered(
                lambda l: l.activity_id == ret_activity
            ).percent

    @api.constrains('excluded_percent')
    def _check_excluded_percent(self):
        for p_ret in self:
            if not (0 <= p_ret.excluded_percent <= 1):
                raise ValidationError(_(
                    "The Excluded Percent Should be a value "
                    "between 0 and 1"
                ))


class ResPartnerAdvanceRetention(models.Model):
    _name = "res.partner.advance.retention"
    _description = "Retention advanced defined in Partner"

    retention_id = fields.Many2one(
        comodel_name='account.journal',
        string='Retention',
        domain=[('type', '=', 'retentions')],
        required=True
    )
    concept_id = fields.Many2one(
        comodel_name='retention.concept',
        string="Concept",
        required=True
    )
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string="Partner"
    )
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


class ResDocumentType(models.Model):
    _name = "res.document.type"
    _description = 'Document type'

    name = fields.Char(string='Document type', size=40)
    afip_code = fields.Char(string='Afip code', size=10)
    verification_required = fields.Boolean(string='Verification required')
    check_duplicated = fields.Boolean(string="Check Duplicated")
    dst_cuit = fields.Boolean(string="Enable DST CUIT")

    def get_website_sale_documents(self, mode='billing'):
        cuit = self.sudo().env.ref('l10n_ar_eynes.document_cuit').name
        cuil = self.sudo().env.ref('l10n_ar_eynes.document_cuil').name
        dni = self.sudo().env.ref('l10n_ar_eynes.document_dni').name
        return self.sudo().search([
            ('name', 'in', (cuit, cuil, dni))
        ])
