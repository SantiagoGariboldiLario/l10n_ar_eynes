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

    customer = fields.Boolean(string='Is Customer')
    supplier = fields.Boolean(string='Is Supplier')
    activity_id = fields.Many2one(
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
    percent = fields.Float('Percent', default=0.00)
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
        string='Company',
        store=True,
    )
    from_padron = fields.Boolean(string="From Padron")

    _sql_constraints = [
        (
            'retention_partner_unique',
            'unique(partner_id, retention_id)',
            _('There must be only one retention of this type configured for '
                + 'the partner')
        )
    ]

    @api.constrains('excluded_percent')
    def _check_excluded_percent(self):
        for p_ret in self:
            if not (0 <= p_ret.excluded_percent <= 1):
                raise ValidationError(
                    _("The Excluded Percent Should be a value "
                      + "between 0 and 1")
                )


class ResPartnerAdvanceRetention(models.Model):
    _name = "res.partner.advance.retention"
    _description = "Retention advanced defined in Partner"

    retention_id = fields.Many2one(
        comodel_name='retention.retention',
        string='Retention',
        required=True)
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
