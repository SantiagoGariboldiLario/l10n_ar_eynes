import base64
import calendar
import io
import json
import logging
import re
from datetime import datetime, time, timedelta

import requests

# pylint: disable=deprecated-odoo-model-method
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


ARBA_A122R_ACTIVITY_SELECTION = [
    ('1', '1 - REGIMEN DE RETEN.EMPRESAS CONSTRUCTORAS'),
    ('6', '6 - REGIMEN GENERAL DE RETENCIONES'),
    ('10', '10 - ACTIVIDAD AGROPECUARIA'),
    ('13', '13 - MUNICIPALIDAD'),
    ('14', '14 - ESTADO NACIONAL'),
    ('15', '15 - ESTADO PROVINCIAL'),
    ('16', '16 - SEGUROS'),
    ('17', '17 - FINANCIERAS/BANCOS'),
    ('20', '20 - INSTITUTO PROV.DE LOTERIA Y CASINOS'),
    ('23', '23 - HONORARIOS'),
]


class ResCompanyArbaA122rActivity(models.Model):
    _name = 'res.company.arba.a122r.activity'
    _description = 'ARBA A122R Activity by Company'
    _order = 'is_default desc, activity_code'

    display_name = fields.Char(compute='_compute_display_name', store=True)
    company_id = fields.Many2one(
        'res.company', required=True, ondelete='cascade'
    )
    activity_code = fields.Selection(
        selection=ARBA_A122R_ACTIVITY_SELECTION,
        required=True,
        string='Actividad',
    )
    is_default = fields.Boolean(string='Habitual')

    _res_company_arba_a122r_activity_unique = models.Constraint(
        'UNIQUE(company_id, activity_code)',
        'La actividad ARBA A122R ya está configurada para esta compañía.',
    )

    @api.constrains('is_default', 'company_id')
    def _check_single_default(self):
        for rec in self:
            if not rec.is_default or not rec.company_id:
                continue
            duplicated = self.search_count(
                [
                    ('company_id', '=', rec.company_id.id),
                    ('is_default', '=', True),
                    ('id', '!=', rec.id),
                ]
            )
            if duplicated:
                raise ValidationError(
                    _(
                        'Solo puede existir una actividad habitual ARBA A122R por compañía.'
                    )
                )

    @api.onchange('is_default')
    def _onchange_is_default(self):
        if self.is_default and self.company_id:
            others = self.company_id.arba_a122r_activity_ids.filtered(
                lambda line: line.id != self.id and line.is_default
            )
            others.update({'is_default': False})

    @api.depends('activity_code')
    def _compute_display_name(self):
        selection_map = dict(ARBA_A122R_ACTIVITY_SELECTION)
        for rec in self:
            rec.display_name = (
                selection_map.get(rec.activity_code)
                or rec.activity_code
                or str(rec.id)
            )


class ArbaA122rDj(models.Model):
    _name = 'arba.a122r.dj'
    _description = 'ARBA A122R DJ Cache'
    _order = 'anio desc, mes desc, quincena desc, id desc'

    display_name = fields.Char(compute='_compute_display_name', store=True)
    company_id = fields.Many2one(
        'res.company',
        required=True,
        index=True,
        default=lambda self: self.env.company,
    )
    cuit_agente = fields.Char(required=True, index=True, readonly=True)
    activity_line_id = fields.Many2one(
        'res.company.arba.a122r.activity',
        string='Actividad',
        domain="[('company_id', '=', company_id)]",
    )
    actividad_id = fields.Integer(required=True)
    anio = fields.Integer(
        required=True, default=lambda self: fields.Date.today().year
    )
    mes = fields.Integer(
        required=True, default=lambda self: fields.Date.today().month
    )
    quincena = fields.Integer(required=True, default=lambda self: 1)
    arba_id_dj = fields.Integer(index=True, readonly=True)
    state = fields.Selection(
        selection=[('open', 'Abierta'), ('closed', 'Cerrada')],
        default='open',
        required=True,
        readonly=True,
    )
    rectificativa = fields.Integer(readonly=True)
    fecha_creacion = fields.Datetime(readonly=True)
    fecha_cierre = fields.Datetime(readonly=True)
    last_sync = fields.Datetime(default=fields.Datetime.now, readonly=True)
    retention_count = fields.Integer(
        string='Retenciones del período',
        compute='_compute_retention_counts',
    )
    informed_retention_count = fields.Integer(
        string='Retenciones informadas',
        compute='_compute_retention_counts',
    )
    informed_record_count = fields.Integer(
        string='Registros informados',
        compute='_compute_retention_counts',
    )

    _arba_a122r_dj_unique_key = models.Constraint(
        'UNIQUE(company_id, cuit_agente, actividad_id, anio, mes, quincena)',
        'Ya existe un registro de DJ para este período y actividad.',
    )

    @api.depends('arba_id_dj', 'anio', 'mes', 'quincena', 'actividad_id')
    def _compute_display_name(self):
        for rec in self:
            if rec.quincena == 0:
                period_label = '%s/%s Mensual' % (
                    rec.anio,
                    str(rec.mes).zfill(2),
                )
            else:
                period_label = '%s/%s Q%s' % (
                    rec.anio,
                    str(rec.mes).zfill(2),
                    rec.quincena,
                )
            dj_label = rec.arba_id_dj or '-'
            rec.display_name = 'DJ %s - %s - Act %s' % (
                dj_label,
                period_label,
                rec.actividad_id,
            )

    @api.model
    def _sanitize_company_cuit(self, company):
        vat = (
            (company.partner_id.vat or '')
            if company and company.partner_id
            else ''
        )
        return ''.join([c for c in vat if c.isdigit()])

    @api.onchange('company_id')
    def _onchange_company_id_defaults(self):
        for rec in self:
            if not rec.company_id:
                continue
            rec.cuit_agente = rec._sanitize_company_cuit(rec.company_id)
            if rec.company_id.arba_a122r_quincena_mode == 'monthly':
                rec.quincena = 0
            elif rec.quincena not in (1, 2):
                rec.quincena = 1
            default_activity = rec.company_id.arba_a122r_activity_ids.filtered(
                lambda a: a.is_default
            )[:1]
            if default_activity:
                rec.activity_line_id = default_activity
                rec.actividad_id = int(default_activity.activity_code)

    @api.onchange('activity_line_id')
    def _onchange_activity_line_id(self):
        for rec in self:
            if rec.activity_line_id:
                rec.actividad_id = int(rec.activity_line_id.activity_code)

    @api.model
    def _find_company_activity_line(self, company, actividad_id):
        if not company or not actividad_id:
            return self.env['res.company.arba.a122r.activity']
        return company.arba_a122r_activity_ids.filtered(
            lambda line: int(line.activity_code) == int(actividad_id)
        )[:1]

    @api.constrains('company_id', 'actividad_id', 'quincena')
    def _check_company_activity(self):
        for rec in self:
            if not rec.company_id:
                continue
            allowed = {
                int(item.activity_code)
                for item in rec.company_id.arba_a122r_activity_ids
            }
            if allowed and rec.actividad_id not in allowed:
                raise ValidationError(
                    _(
                        'La actividad %(activity)s no está habilitada para la compañía %(company)s.',
                        activity=rec.actividad_id,
                        company=rec.company_id.display_name,
                    )
                )
            if (
                rec.company_id.arba_a122r_quincena_mode == 'monthly'
                and rec.quincena != 0
            ):
                raise ValidationError(
                    _(
                        'La compañía está en modo mensual. La quincena debe ser Mensual (0).'
                    )
                )
            if (
                rec.company_id.arba_a122r_quincena_mode == 'biweekly'
                and rec.quincena
                not in (
                    1,
                    2,
                )
            ):
                raise ValidationError(
                    _(
                        'La compañía está en modo quincenal. La quincena debe ser 1 o 2.'
                    )
                )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            company = self.env['res.company'].browse(
                vals.get('company_id') or self.env.company.id
            )
            if vals.get('activity_line_id') and not vals.get('actividad_id'):
                activity = self.env['res.company.arba.a122r.activity'].browse(
                    vals['activity_line_id']
                )
                if activity:
                    vals['actividad_id'] = int(activity.activity_code)
            elif vals.get('actividad_id') and not vals.get('activity_line_id'):
                activity = self._find_company_activity_line(
                    company, vals['actividad_id']
                )
                if activity:
                    vals['activity_line_id'] = activity.id
            if not vals.get('cuit_agente'):
                vals['cuit_agente'] = self._sanitize_company_cuit(company)
            if not vals.get('anio'):
                vals['anio'] = fields.Date.today().year
            if not vals.get('mes'):
                vals['mes'] = fields.Date.today().month
            if 'quincena' not in vals:
                vals['quincena'] = (
                    0 if company.arba_a122r_quincena_mode == 'monthly' else 1
                )
        return super().create(vals_list)

    def _get_period_date_range(self):
        self.ensure_one()
        start_date = fields.Date.from_string(
            '%04d-%02d-01' % (self.anio, self.mes)
        )
        last_day = calendar.monthrange(self.anio, self.mes)[1]
        end_date = fields.Date.from_string(
            '%04d-%02d-%02d' % (self.anio, self.mes, last_day)
        )
        if self.quincena == 1:
            end_date = fields.Date.from_string(
                '%04d-%02d-15' % (self.anio, self.mes)
            )
        elif self.quincena == 2:
            start_date = fields.Date.from_string(
                '%04d-%02d-16' % (self.anio, self.mes)
            )
        return start_date, end_date

    def _get_period_retention_domain(self):
        self.ensure_one()
        start_date, end_date = self._get_period_date_range()
        return [
            ('payment_order_id.company_id', '=', self.company_id.id),
            ('payment_order_id.type', '=', 'payment'),
            ('payment_order_id.date', '>=', start_date),
            ('payment_order_id.date', '<=', end_date),
            ('retention_id.retention_type', '=', 'gross_income'),
            ('retention_id.inform_arba', '=', True),
        ]

    def _get_period_retention_record_domain(self):
        self.ensure_one()
        start_date, end_date = self._get_period_date_range()
        return [
            ('company_id', '=', self.company_id.id),
            ('payment_order_id.type', '=', 'payment'),
            ('payment_order_id.date', '>=', start_date),
            ('payment_order_id.date', '<=', end_date),
            ('arba_actividad_id_used', '=', self.actividad_id),
        ]

    def _compute_retention_counts(self):
        RetentionLine = self.env['account.payment.order.retention.line']
        RetentionRecord = self.env['arba.a122r.retention.record']
        for record in self:
            line_domain = record._get_period_retention_domain()
            record_domain = record._get_period_retention_record_domain()
            record.retention_count = RetentionLine.search_count(line_domain)
            record.informed_retention_count = RetentionLine.search_count(
                line_domain
                + [('arba_sync_state', 'in', ('sent', 'observed', 'deleted'))]
            )
            record.informed_record_count = RetentionRecord.search_count(
                record_domain
                + [('arba_sync_state', 'in', ('sent', 'observed', 'deleted'))]
            )

    def action_view_period_retentions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Retenciones ARBA del período'),
            'res_model': 'account.payment.order.retention.line',
            'view_mode': 'list,form',
            'domain': self._get_period_retention_domain(),
            'context': {'search_default_group_by_payment_order_id': 1},
        }

    def action_view_period_informed_retentions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Retenciones ARBA informadas'),
            'res_model': 'account.payment.order.retention.line',
            'view_mode': 'list,form',
            'domain': self._get_period_retention_domain()
            + [('arba_sync_state', 'in', ('sent', 'observed', 'deleted'))],
            'context': {'search_default_group_by_payment_order_id': 1},
        }

    def action_view_period_informed_records(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Registros ARBA informados'),
            'res_model': 'arba.a122r.retention.record',
            'view_mode': 'list,form',
            'views': [
                (
                    self.env.ref(
                        'l10n_ar_eynes.view_arba_a122r_retention_record_tree'
                    ).id,
                    'list',
                ),
                (
                    self.env.ref(
                        'l10n_ar_eynes.view_arba_a122r_retention_record_form'
                    ).id,
                    'form',
                ),
            ],
            'domain': self._get_period_retention_record_domain()
            + [('arba_sync_state', 'in', ('sent', 'observed', 'deleted'))],
            'context': {'search_default_group_by_payment_order_id': 1},
        }

    def action_mark_closed(self):
        for rec in self:
            rec.write(
                {
                    'state': 'closed',
                    'fecha_cierre': fields.Datetime.now(),
                }
            )
        return True

    def action_mark_open(self):
        for rec in self:
            rec.write(
                {
                    'state': 'open',
                    'fecha_cierre': False,
                }
            )
        return True

    def action_open_remote_dj(self):
        self.ensure_one()
        service = self.env['arba.a122r.service']
        dj_cache = service._get_or_create_dj(
            self.company_id,
            fields.Date.from_string(
                '%04d-%02d-%02d'
                % (
                    self.anio,
                    self.mes,
                    1 if self.quincena in (0, 1) else 16,
                )
            ),
            actividad_id=self.actividad_id,
        )
        self.write(
            {
                'arba_id_dj': dj_cache.arba_id_dj,
                'state': 'open',
                'fecha_cierre': False,
                'last_sync': fields.Datetime.now(),
            }
        )
        return True


class ArbaA122rRequestLog(models.Model):
    _name = 'arba.a122r.request.log'
    _description = 'ARBA A122R Request Log'
    _order = 'create_date desc, id desc'

    company_id = fields.Many2one('res.company', required=True, index=True)
    payment_order_id = fields.Many2one('account.payment.order', index=True)
    retention_record_id = fields.Many2one(
        'arba.a122r.retention.record',
        string='Registro ARBA persistente',
        index=True,
        ondelete='set null',
    )
    retention_line_id = fields.Many2one(
        'account.payment.order.retention.line', index=True, ondelete='set null'
    )
    endpoint = fields.Char(required=True)
    method = fields.Char(required=True)
    status_code = fields.Integer()
    state = fields.Selection(
        [('ok', 'OK'), ('error', 'Error')], required=True, default='ok'
    )
    request_payload = fields.Text()
    response_payload = fields.Text()
    error_message = fields.Text()


class ArbaA122rComprobanteHistory(models.Model):
    _name = 'arba.a122r.comprobante.history'
    _description = 'ARBA A122R Comprobante History'
    _order = 'create_date desc, id desc'

    retention_record_id = fields.Many2one(
        'arba.a122r.retention.record',
        string='Registro ARBA persistente',
        index=True,
        ondelete='cascade',
    )
    retention_line_id = fields.Many2one(
        'account.payment.order.retention.line',
        string='Línea de retención',
        index=True,
        ondelete='set null',
    )
    payment_order_id = fields.Many2one(
        'account.payment.order',
        index=True,
        readonly=True,
    )
    company_id = fields.Many2one('res.company', readonly=True, index=True)
    action = fields.Selection(
        [('send', 'Envío'), ('delete', 'Baja')], required=True, default='send'
    )
    state = fields.Selection(
        [
            ('sent', 'Informada'),
            ('observed', 'Observada'),
            ('deleted', 'Dada de baja'),
        ],
        required=True,
        default='sent',
    )
    arba_id_dj = fields.Integer()
    arba_id_comprobante = fields.Integer()
    arba_nro_emision = fields.Char()
    arba_n_transaccion_agente = fields.Char()
    notes = fields.Char()

    def action_arba_download_pdf(self):
        self.ensure_one()
        if not self.arba_id_comprobante:
            raise ValidationError(
                _(
                    'Esta línea del historial no tiene ID de comprobante ARBA para descargar PDF.'
                )
            )
        company = (
            self.company_id
            or self.payment_order_id.company_id
            or self.retention_line_id.payment_order_id.company_id
        )
        payment_order = (
            self.payment_order_id or self.retention_line_id.payment_order_id
        )
        service = self.env['arba.a122r.service']
        response = service._do_request(
            company,
            method='GET',
            path='/external/comprobantePdf',
            params={'id': int(self.arba_id_comprobante)},
        )
        service._create_request_log(
            company,
            '/external/comprobantePdf',
            'GET',
            payload={'id': int(self.arba_id_comprobante)},
            response='binary/pdf' if isinstance(response, bytes) else response,
            status_code=200,
            payment_order=payment_order,
            retention_record=self.retention_record_id,
            retention_line=self.retention_line_id,
        )
        pdf_data = service._extract_pdf_bytes(response)
        attachment = self.env['ir.attachment'].create(
            {
                'name': 'ARBA-History-Comprobante-%s.pdf'
                % (self.arba_id_comprobante or self.id),
                'type': 'binary',
                'datas': base64.b64encode(pdf_data),
                'res_model': self._name,
                'res_id': self.id,
                'mimetype': 'application/pdf',
            }
        )
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'self',
        }


class ArbaA122rRetentionRecord(models.Model):
    _name = 'arba.a122r.retention.record'
    _description = 'Registro persistente de retención ARBA A122R'
    _order = 'create_date desc, id desc'

    name = fields.Char(compute='_compute_name', string='Descripción')
    company_id = fields.Many2one('res.company', required=True, index=True)
    payment_order_id = fields.Many2one(
        'account.payment.order', required=True, index=True, ondelete='cascade'
    )
    partner_id = fields.Many2one('res.partner', index=True, ondelete='set null')
    current_retention_line_id = fields.Many2one(
        'account.payment.order.retention.line',
        string='Línea actual',
        index=True,
        ondelete='set null',
    )
    current_history_entry_id = fields.Many2one(
        'arba.a122r.comprobante.history',
        string='Último comprobante',
        ondelete='set null',
    )
    current = fields.Boolean(default=True, index=True)
    lifecycle_state = fields.Selection(
        [
            ('linked', 'Vinculada'),
            ('orphaned', 'Huérfana'),
            ('superseded', 'Reemplazada'),
        ],
        default='linked',
        required=True,
        index=True,
    )
    superseded_by_id = fields.Many2one(
        'arba.a122r.retention.record',
        string='Reemplazada por',
        ondelete='set null',
    )
    replaces_record_id = fields.Many2one(
        'arba.a122r.retention.record',
        string='Reemplaza a',
        ondelete='set null',
    )
    retention_id = fields.Many2one(
        'account.journal',
        string='Retención',
        ondelete='set null',
    )
    tax_id = fields.Many2one(
        'account.tax', string='Impuesto', ondelete='set null'
    )
    base_amount = fields.Float(string='Base imponible', digits='Account')
    retention_amount = fields.Float(
        string='Importe retención', digits='Account'
    )
    alicuota = fields.Float(string='Alícuota', digits='Account')
    arba_fecha_operacion = fields.Date(copy=False)
    arba_actividad_id_used = fields.Integer(copy=False, readonly=True)
    cuit_contribuyente = fields.Char(copy=False)
    razon_social_contribuyente = fields.Char(copy=False)
    sucursal = fields.Char(copy=False)
    arba_sync_state = fields.Selection(
        selection=[
            ('pending', 'Pendiente'),
            ('sent', 'Informada'),
            ('observed', 'Observada'),
            ('error', 'Error'),
            ('deleted', 'Dada de baja'),
        ],
        default=False,
        copy=False,
        index=True,
    )
    arba_id_dj = fields.Integer(copy=False, index=True)
    arba_id_comprobante = fields.Integer(copy=False, index=True)
    arba_nro_emision = fields.Char(copy=False)
    arba_observacion = fields.Char(copy=False)
    arba_last_request = fields.Text(copy=False)
    arba_last_response = fields.Text(copy=False)
    arba_last_error = fields.Text(copy=False)
    arba_n_transaccion_agente = fields.Char(copy=False, index=True)
    arba_pdf_attachment_id = fields.Many2one(
        'ir.attachment',
        copy=False,
        readonly=True,
        string='PDF comprobante ARBA',
    )
    history_ids = fields.One2many(
        'arba.a122r.comprobante.history',
        'retention_record_id',
        string='Historial de comprobantes',
        readonly=True,
    )
    request_log_ids = fields.One2many(
        'arba.a122r.request.log',
        'retention_record_id',
        string='Solicitudes ARBA',
        readonly=True,
    )

    @api.depends(
        'payment_order_id.number',
        'arba_n_transaccion_agente',
        'partner_id',
        'arba_id_comprobante',
    )
    def _compute_name(self):
        for rec in self:
            parts = [rec.payment_order_id.number or _('Sin OP')]
            if rec.arba_n_transaccion_agente:
                parts.append(_('Tx %s') % rec.arba_n_transaccion_agente)
            if rec.arba_id_comprobante:
                parts.append(_('Comp. %s') % rec.arba_id_comprobante)
            if rec.partner_id:
                parts.append(rec.partner_id.display_name)
            rec.name = ' - '.join(parts)

    def action_open_current_line(self):
        self.ensure_one()
        if not self.current_retention_line_id:
            raise UserError(
                _(
                    'Este registro persistente ya no tiene una línea de retención vigente.'
                )
            )
        return {
            'type': 'ir.actions.act_window',
            'name': _('Línea de retención'),
            'res_model': 'account.payment.order.retention.line',
            'res_id': self.current_retention_line_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_arba_download_pdf(self):
        self.ensure_one()
        service = self.env['arba.a122r.service']
        force_refresh = self.arba_sync_state == 'deleted'
        attachment = service.get_comprobante_pdf_from_record(
            self, force_refresh=force_refresh
        )
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'self',
        }


class ResCompany(models.Model):
    _inherit = 'res.company'

    arba_a122r_enabled = fields.Boolean(string='Habilitar ARBA A122R digital')
    arba_a122r_enforced = fields.Boolean(
        string='A122R obligatorio',
        help='Si se activa, se bloquea el flujo ARBA tradicional (TXT/certificado) para retenciones ARBA.',
    )
    arba_a122r_mode = fields.Selection(
        selection=[('testing', 'Pruebas'), ('production', 'Producción')],
        default='testing',
        required=True,
        string='Modo',
    )
    arba_a122r_base_url = fields.Char(
        string='URL base API A122R',
        default='https://app2.test.arba.gov.ar/a122rSrv/api',
    )
    arba_a122r_token_url = fields.Char(
        string='URL token OAuth',
        default='https://idp.test.arba.gov.ar/realms/ARBA/protocol/openid-connect/token',
    )
    arba_a122r_client_id = fields.Char(string='Client ID ARBA')
    arba_a122r_client_secret = fields.Char(string='Client Secret ARBA')
    arba_a122r_username = fields.Char(
        string='Usuario OAuth ARBA',
        help='Generalmente el CUIT del agente.',
    )
    arba_a122r_password = fields.Char(string='Clave OAuth ARBA (CIT)')
    arba_a122r_timeout = fields.Integer(default=30, string='Timeout (segundos)')
    arba_a122r_block_validation_on_error = fields.Boolean(
        string='Bloquear validación de pago si falla ARBA',
        default=True,
        help=(
            'Si está activo, al validar una orden de pago con retenciones ARBA '
            'se cancela la validación cuando falla la información en A122R.'
        ),
    )
    arba_a122r_sucursal = fields.Char(default='1', string='Sucursal')
    arba_a122r_actividad_id = fields.Integer(default=6)
    arba_a122r_activity_ids = fields.One2many(
        'res.company.arba.a122r.activity',
        'company_id',
        string='Actividades ARBA A122R',
    )
    arba_a122r_access_token = fields.Text(copy=False, string='Token actual')
    arba_a122r_token_expiration = fields.Datetime(
        copy=False, string='Vencimiento token'
    )
    arba_a122r_quincena_mode = fields.Selection(
        selection=[('biweekly', 'Quincenal (1/2)'), ('monthly', 'Mensual (0)')],
        default='biweekly',
        required=True,
        string='Periodicidad DJ',
    )

    def action_arba_a122r_test_connection(self):
        self.ensure_one()
        self.env['arba.a122r.service']._get_token(self, force_refresh=True)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('ARBA A122R'),
                'message': _(
                    'Conexión validada correctamente. Las credenciales OAuth de ARBA son válidas.'
                ),
                'type': 'success',
                'sticky': False,
            },
        }

    @api.constrains('arba_a122r_sucursal')
    def _check_arba_a122r_sucursal(self):
        for company in self:
            if (
                company.arba_a122r_sucursal
                and not company.arba_a122r_sucursal.isdigit()
            ):
                raise ValidationError(
                    _('La sucursal ARBA A122R debe ser numérica.')
                )

    @api.onchange('arba_a122r_mode')
    def _onchange_arba_a122r_mode(self):
        if self.arba_a122r_mode == 'production':
            self.arba_a122r_base_url = 'https://app.arba.gov.ar/a122rSrv/api'
            self.arba_a122r_token_url = 'https://idp.arba.gov.ar/realms/ARBA/protocol/openid-connect/token'
        elif self.arba_a122r_mode == 'testing':
            self.arba_a122r_base_url = (
                'https://app2.test.arba.gov.ar/a122rSrv/api'
            )
            self.arba_a122r_token_url = 'https://idp.test.arba.gov.ar/realms/ARBA/protocol/openid-connect/token'

    @api.constrains('arba_a122r_enabled', 'arba_a122r_activity_ids')
    def _check_arba_a122r_default_activity(self):
        for company in self:
            if not company.arba_a122r_enabled:
                continue
            if not company.arba_a122r_activity_ids:
                if not company.arba_a122r_actividad_id:
                    raise ValidationError(
                        _(
                            'Debe configurar al menos una actividad ARBA A122R en la compañía.'
                        )
                    )
                continue
            defaults = company.arba_a122r_activity_ids.filtered(
                lambda line: line.is_default
            )
            if len(defaults) != 1:
                raise ValidationError(
                    _(
                        'Debe existir exactamente una actividad habitual ARBA A122R en la compañía.'
                    )
                )

    def _get_default_arba_a122r_activity_code(self):
        self.ensure_one()
        default_line = self.arba_a122r_activity_ids.filtered(
            lambda line: line.is_default
        )[:1]
        if default_line:
            return int(default_line.activity_code)
        if self.arba_a122r_actividad_id:
            return int(self.arba_a122r_actividad_id)
        return False

    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        companies._ensure_arba_a122r_activity_defaults()
        return companies

    def write(self, vals):
        res = super().write(vals)
        self._ensure_arba_a122r_activity_defaults()
        return res

    def _ensure_arba_a122r_activity_defaults(self):
        Activity = self.env['res.company.arba.a122r.activity']
        for company in self:
            if company.arba_a122r_activity_ids:
                continue
            fallback = str(company.arba_a122r_actividad_id or 6)
            if fallback not in {
                code for code, _name in ARBA_A122R_ACTIVITY_SELECTION
            }:
                fallback = '6'
            Activity.create(
                {
                    'company_id': company.id,
                    'activity_code': fallback,
                    'is_default': True,
                }
            )

    @api.model
    def _register_hook(self):
        res = super()._register_hook()
        self.sudo().search([])._ensure_arba_a122r_activity_defaults()
        return res


class ArbaA122rService(models.AbstractModel):
    _name = 'arba.a122r.service'
    _description = 'ARBA A122R Service Client'

    @api.model
    def _sanitize_cuit(self, cuit):
        digits = ''.join([c for c in (cuit or '') if c.isdigit()])
        if len(digits) != 11:
            raise ValidationError(_('CUIT inválido: %s') % cuit)
        return digits

    @api.model
    def _iso_datetime_from_date(self, date_value):
        dt = datetime.combine(fields.Date.to_date(date_value), time(12, 0, 0))
        return dt.strftime('%Y-%m-%dT%H:%M:%S')

    @api.model
    def _normalize_transaction_number(self, retention_line):
        """
        ARBA validates this field as numeric. We keep it deterministic so retries
        are idempotent and do not create different transaction ids.
        """
        current = retention_line.arba_n_transaccion_agente or ''
        digits = ''.join([c for c in str(current) if c.isdigit()])
        if not digits:
            digits = str(retention_line.id)
        # Keep a conservative max length for external validators.
        return digits[:20]

    @api.model
    def _next_transaction_number(self, retention_line):
        """
        Después de una baja, ARBA exige un nuevo número de transacción.
        Genera un correlativo numérico estable basado en el id de línea.
        """
        base = str(retention_line.id)
        history_numbers = retention_line.arba_history_ids.mapped(
            'arba_n_transaccion_agente'
        )
        current = retention_line.arba_n_transaccion_agente or ''
        candidates = [current] + history_numbers
        max_suffix = -1
        for candidate in candidates:
            digits = ''.join([c for c in str(candidate or '') if c.isdigit()])
            if not digits:
                continue
            if digits == base:
                max_suffix = max(max_suffix, 0)
                continue
            if digits.startswith(base):
                suffix = digits[len(base) :]
                if suffix.isdigit():
                    max_suffix = max(max_suffix, int(suffix))
        next_suffix = max_suffix + 1
        if next_suffix <= 0:
            return base[:20]

        line_model = self.env['account.payment.order.retention.line']
        while True:
            suffix = str(next_suffix).zfill(2)
            prefix_len = max(1, 20 - len(suffix))
            candidate = '%s%s' % (base[:prefix_len], suffix)
            exists = line_model.search_count(
                [
                    ('id', '!=', retention_line.id),
                    ('arba_n_transaccion_agente', '=', candidate),
                ]
            )
            if not exists:
                return candidate
            next_suffix += 1

    @api.model
    def _get_or_create_retention_record(self, retention_line):
        record = retention_line.arba_retention_record_id
        tax = retention_line._get_retention_tax()
        if record:
            vals = {'current_retention_line_id': retention_line.id}
            if record.lifecycle_state != 'linked':
                vals.update({'lifecycle_state': 'linked', 'current': True})
            record.sudo().write(vals)
            return record
        record = (
            self.env['arba.a122r.retention.record']
            .sudo()
            .create(
                {
                    'company_id': retention_line.payment_order_id.company_id.id,
                    'payment_order_id': retention_line.payment_order_id.id,
                    'partner_id': (
                        retention_line.partner_id
                        or retention_line.payment_order_id.partner_id
                    ).id,
                    'current_retention_line_id': retention_line.id,
                    'current': True,
                    'lifecycle_state': 'linked',
                    'retention_id': retention_line.retention_id.id,
                    'tax_id': tax.id,
                }
            )
        )
        retention_line.sudo().write({'arba_retention_record_id': record.id})
        return record

    @api.model
    def orphan_retention_records(self, retention_lines):
        records = retention_lines.mapped('arba_retention_record_id').filtered(
            lambda rec: rec
        )
        if not records:
            return
        records.sudo().write(
            {
                'current_retention_line_id': False,
                'lifecycle_state': 'orphaned',
                'current': False,
            }
        )
        retention_lines.sudo().write({'arba_retention_record_id': False})

    @api.model
    def _build_record_snapshot_from_line(self, retention_line, payload=False):
        partner = (
            retention_line.partner_id
            or retention_line.payment_order_id.partner_id
        )
        tax = retention_line._get_retention_tax()
        snapshot = {
            'company_id': retention_line.payment_order_id.company_id.id,
            'payment_order_id': retention_line.payment_order_id.id,
            'partner_id': partner.id if partner else False,
            'current_retention_line_id': retention_line.id,
            'retention_id': retention_line.retention_id.id,
            'tax_id': tax.id,
            'base_amount': retention_line.base,
            'retention_amount': retention_line.amount,
            'arba_fecha_operacion': retention_line.arba_fecha_operacion,
            'arba_actividad_id_used': retention_line.arba_actividad_id_used,
            'arba_sync_state': retention_line.arba_sync_state,
            'arba_id_dj': retention_line.arba_id_dj,
            'arba_id_comprobante': retention_line.arba_id_comprobante,
            'arba_nro_emision': retention_line.arba_nro_emision,
            'arba_observacion': retention_line.arba_observacion,
            'arba_last_request': retention_line.arba_last_request,
            'arba_last_response': retention_line.arba_last_response,
            'arba_last_error': retention_line.arba_last_error,
            'arba_n_transaccion_agente': retention_line.arba_n_transaccion_agente,
            'cuit_contribuyente': (
                ''.join([c for c in (partner.vat or '') if c.isdigit()])
                if partner
                else False
            ),
            'razon_social_contribuyente': partner.name if partner else False,
            'sucursal': retention_line.payment_order_id.company_id.arba_a122r_sucursal,
        }
        payload = payload or {}
        if payload.get('alicuota') is not None:
            snapshot['alicuota'] = payload.get('alicuota')
        return snapshot

    @api.model
    def _ensure_record_snapshot_from_line(
        self, retention_line, retention_record=False
    ):
        record = retention_record or self._get_or_create_retention_record(
            retention_line
        )
        record.sudo().write(
            self._build_record_snapshot_from_line(retention_line)
        )
        self._sync_line_from_record(record, retention_line)
        return record

    @api.model
    def _sync_line_from_record(self, record, retention_line=False):
        line = retention_line or record.current_retention_line_id
        if not line:
            return
        line.sudo().write(
            {
                'arba_retention_record_id': record.id,
                'arba_sync_state': record.arba_sync_state,
                'arba_id_dj': record.arba_id_dj,
                'arba_id_comprobante': record.arba_id_comprobante,
                'arba_nro_emision': record.arba_nro_emision,
                'arba_observacion': record.arba_observacion,
                'arba_last_request': record.arba_last_request,
                'arba_last_response': record.arba_last_response,
                'arba_last_error': record.arba_last_error,
                'arba_n_transaccion_agente': record.arba_n_transaccion_agente,
                'arba_fecha_operacion': record.arba_fecha_operacion,
                'arba_actividad_id_used': record.arba_actividad_id_used,
                'arba_pdf_attachment_id': record.arba_pdf_attachment_id.id,
            }
        )

    @api.model
    def _create_comprobante_history(
        self, retention_line, retention_record, action, state, notes=False
    ):
        history = (
            self.env['arba.a122r.comprobante.history']
            .sudo()
            .create(
                {
                    'retention_record_id': retention_record.id,
                    'retention_line_id': (
                        retention_line.id if retention_line else False
                    ),
                    'payment_order_id': retention_record.payment_order_id.id,
                    'company_id': retention_record.company_id.id,
                    'action': action,
                    'state': state,
                    'arba_id_dj': retention_record.arba_id_dj or 0,
                    'arba_id_comprobante': retention_record.arba_id_comprobante
                    or 0,
                    'arba_nro_emision': retention_record.arba_nro_emision
                    or False,
                    'arba_n_transaccion_agente': retention_record.arba_n_transaccion_agente
                    or False,
                    'notes': notes or False,
                }
            )
        )
        retention_record.sudo().write({'current_history_entry_id': history.id})
        return history

    @api.model
    def _extract_pdf_bytes(self, response):
        if isinstance(response, bytes):
            if not response:
                raise ValidationError(_('ARBA devolvió un PDF vacío.'))
            if response.lstrip().startswith(b'%PDF'):
                return response
            sample = response[:200].decode('utf-8', errors='ignore')
            if '<html' in sample.lower():
                raise ValidationError(
                    _(
                        'ARBA devolvió contenido no PDF al solicitar el comprobante. '
                        'Reintentá más tarde. Detalle: %s'
                    )
                    % sample
                )
            return response
        if isinstance(response, dict):
            base64_pdf = (
                response.get('pdf')
                or response.get('archivo')
                or response.get('file')
                or response.get('data')
                or response.get('content')
            )
            if base64_pdf:
                return base64.b64decode(base64_pdf)
        if isinstance(response, list):
            return b''.join(
                [base64.b64decode(item) for item in response if item]
            )
        if isinstance(response, str):
            return base64.b64decode(response)
        raise ValidationError(
            _('Formato de respuesta PDF de ARBA no esperado.')
        )

    @api.model
    def _store_comprobante_pdf_attachment(self, retention_record, pdf_data):
        if not pdf_data:
            return False
        vals = {
            'name': 'ARBA-Comprobante-%s.pdf'
            % (retention_record.arba_id_comprobante or retention_record.id),
            'type': 'binary',
            'datas': base64.b64encode(pdf_data),
            'res_model': 'arba.a122r.retention.record',
            'res_id': retention_record.id,
            'mimetype': 'application/pdf',
        }
        attachment = retention_record.arba_pdf_attachment_id.sudo()
        if attachment:
            attachment.write(vals)
        else:
            attachment = self.env['ir.attachment'].sudo().create(vals)
            retention_record.sudo().write(
                {'arba_pdf_attachment_id': attachment.id}
            )
        if retention_record.current_retention_line_id:
            retention_record.current_retention_line_id.sudo().write(
                {'arba_pdf_attachment_id': attachment.id}
            )
        return attachment

    @api.model
    def _get_cached_comprobante_pdf(self, retention_record):
        attachment = retention_record.arba_pdf_attachment_id
        if attachment and attachment.datas:
            return base64.b64decode(attachment.datas)
        return False

    @api.model
    def _ensure_company_config(self, company):
        company._ensure_arba_a122r_activity_defaults()
        missing = []
        required = [
            ('arba_a122r_base_url', 'URL base API A122R'),
            ('arba_a122r_token_url', 'URL token OAuth'),
            ('arba_a122r_client_id', 'Client ID ARBA'),
            ('arba_a122r_client_secret', 'Client Secret ARBA'),
            ('arba_a122r_username', 'Usuario OAuth ARBA'),
            ('arba_a122r_password', 'Clave OAuth ARBA (CIT)'),
            ('arba_a122r_sucursal', 'Sucursal'),
        ]
        for field_name, label in required:
            if not getattr(company, field_name):
                missing.append(label)
        if missing:
            raise ValidationError(
                _(
                    'La configuración ARBA A122R de la compañía está incompleta: %s'
                )
                % ', '.join(missing)
            )
        if not company._get_default_arba_a122r_activity_code():
            raise ValidationError(
                _(
                    'Debe definir una actividad ARBA A122R habitual en la configuración de la compañía.'
                )
            )

    @api.model
    def _get_token(self, company, force_refresh=False):
        self._ensure_company_config(company)
        now = fields.Datetime.now()
        if (
            not force_refresh
            and company.arba_a122r_access_token
            and company.arba_a122r_token_expiration
            and fields.Datetime.to_datetime(company.arba_a122r_token_expiration)
            > fields.Datetime.to_datetime(now) + timedelta(seconds=30)
        ):
            return company.arba_a122r_access_token
        data = {
            'client_id': company.arba_a122r_client_id,
            'client_secret': company.arba_a122r_client_secret,
            'username': company.arba_a122r_username,
            'password': company.arba_a122r_password,
            'grant_type': 'password',
            'scope': 'openid',
        }
        response = requests.post(
            company.arba_a122r_token_url,
            data=data,
            timeout=company.arba_a122r_timeout or 30,
        )
        if response.status_code >= 400:
            raise ValidationError(
                _('No se pudo autenticar contra OAuth de ARBA: %s')
                % response.text
            )
        payload = response.json()
        token = payload.get('access_token')
        if not token:
            raise ValidationError(
                _('ARBA no devolvió access_token en la autenticación.')
            )
        expires_in = int(payload.get('expires_in') or 0)
        expiration = fields.Datetime.to_datetime(now) + timedelta(
            seconds=max(30, expires_in - 60)
        )
        company.sudo().write(
            {
                'arba_a122r_access_token': token,
                'arba_a122r_token_expiration': fields.Datetime.to_string(
                    expiration
                ),
            }
        )
        return token

    @api.model
    def _do_request(  # noqa: C901
        self, company, method, path, token=None, payload=None, params=None
    ):
        base_url = (company.arba_a122r_base_url or '').rstrip('/')
        url = '%s%s' % (base_url, path)
        bearer = token or self._get_token(company)

        def _request_with_bearer(access_token):
            headers = {
                'Authorization': 'Bearer %s' % access_token,
                'Accept': 'application/json',
            }
            if payload is not None:
                headers['Content-Type'] = 'application/json'
            return requests.request(
                method,
                url,
                headers=headers,
                json=payload,
                params=params,
                timeout=company.arba_a122r_timeout or 30,
            )

        try:
            response = _request_with_bearer(bearer)
        except requests.exceptions.Timeout as err:
            raise ValidationError(
                _(
                    'Tiempo de espera agotado al conectar con ARBA A122R (%(method)s %(path)s). '
                    'Reintentá en unos minutos.',
                    method=method,
                    path=path,
                )
            ) from err
        except requests.exceptions.RequestException as err:
            raise ValidationError(
                _(
                    'No se pudo conectar con ARBA A122R (%(method)s %(path)s): %(error)s',
                    method=method,
                    path=path,
                    error=str(err),
                )
            ) from err
        if response.status_code == 401 and not token:
            # Cached token may be expired/revoked. Refresh once and retry.
            company.sudo().write(
                {
                    'arba_a122r_access_token': False,
                    'arba_a122r_token_expiration': False,
                }
            )
            fresh_bearer = self._get_token(company)
            try:
                response = _request_with_bearer(fresh_bearer)
            except requests.exceptions.Timeout as err:
                raise ValidationError(
                    _(
                        'Tiempo de espera agotado al conectar con ARBA A122R (%(method)s %(path)s). '
                        'Reintentá en unos minutos.',
                        method=method,
                        path=path,
                    )
                ) from err
            except requests.exceptions.RequestException as err:
                raise ValidationError(
                    _(
                        'No se pudo conectar con ARBA A122R (%(method)s %(path)s): %(error)s',
                        method=method,
                        path=path,
                        error=str(err),
                    )
                ) from err
        content_type = response.headers.get('Content-Type', '')
        if response.status_code >= 400:
            error_message = response.text
            if 'application/json' in content_type:
                try:
                    error_json = response.json()
                    error_message = error_json.get('message') or response.text
                except Exception as err:
                    _logger.debug(
                        'No se pudo parsear JSON de error ARBA (%s %s): %s',
                        method,
                        path,
                        str(err),
                    )
            raise ValidationError(
                _('ARBA A122R request failed (%(code)s): %(message)s')
                % {'code': response.status_code, 'message': error_message}
            )
        if 'application/json' in content_type:
            if not (response.text or '').strip():
                return {}
            try:
                return response.json()
            except Exception:
                # Some ARBA endpoints may respond with non-JSON content while
                # still declaring JSON content type.
                return response.content
        return response.content

    @api.model
    def _create_request_log(
        self,
        company,
        path,
        method,
        payload=None,
        response=None,
        error_message=None,
        status_code=False,
        payment_order=False,
        retention_record=False,
        retention_line=False,
    ):
        try:
            self.env['arba.a122r.request.log'].sudo().create(
                {
                    'company_id': company.id,
                    'payment_order_id': (
                        payment_order.id if payment_order else False
                    ),
                    'retention_record_id': (
                        retention_record.id if retention_record else False
                    ),
                    'retention_line_id': (
                        retention_line.id if retention_line else False
                    ),
                    'endpoint': path,
                    'method': method,
                    'status_code': status_code or 0,
                    'state': 'error' if error_message else 'ok',
                    'request_payload': (
                        json.dumps(payload, ensure_ascii=True)
                        if isinstance(payload, (dict, list))
                        else (str(payload) if payload else False)
                    ),
                    'response_payload': (
                        json.dumps(response, ensure_ascii=True)
                        if isinstance(response, (dict, list))
                        else (str(response) if response else False)
                    ),
                    'error_message': error_message or False,
                }
            )
        except Exception:
            _logger.exception(
                'Could not persist ARBA A122R request log for endpoint %s %s',
                method,
                path,
            )

    @api.model
    def _get_period_values(self, company, date_value):
        date_value = fields.Date.to_date(date_value)
        quincena = 0
        if company.arba_a122r_quincena_mode == 'biweekly':
            quincena = 1 if date_value.day <= 15 else 2
        return date_value.year, date_value.month, quincena

    @api.model
    def _extract_dj_id(self, response_data):
        if isinstance(response_data, dict):
            return response_data.get('id') or response_data.get('idDj')
        if isinstance(response_data, list) and response_data:
            item = response_data[0]
            if isinstance(item, dict):
                return item.get('id') or item.get('idDj')
        return False

    @api.model
    def _extract_dj_id_from_error(self, error_text):
        if not error_text:
            return False
        match = re.search(r'(?:DDJJ\\s*Id|idDj)\\s*[:=]\\s*(\\d+)', error_text)
        return int(match.group(1)) if match else False

    @api.model
    def _extract_comprobante_values(self, response_data):
        values = {'id': False, 'nroEmision': False, 'observacion': False}
        if not isinstance(response_data, dict):
            return values
        values['id'] = response_data.get('id') or response_data.get(
            'idComprobante'
        )
        values['nroEmision'] = response_data.get(
            'nroEmision'
        ) or response_data.get('nroemision')
        values['observacion'] = response_data.get(
            'observacion'
        ) or response_data.get('observaciones')
        return values

    @api.model
    def _extract_comprobante_from_collection(
        self, response_data, transaction_number=False
    ):
        if isinstance(response_data, dict):
            return self._extract_comprobante_values(response_data)
        if not isinstance(response_data, list):
            return {'id': False, 'nroEmision': False, 'observacion': False}
        tx = ''.join([c for c in str(transaction_number or '') if c.isdigit()])
        for item in response_data:
            if not isinstance(item, dict):
                continue
            item_tx = str(
                item.get('ntransaccionAgente')
                or item.get('nTransaccionAgente')
                or item.get('nroTransaccionAgente')
                or item.get('nrotransaccionAgente')
                or ''
            )
            item_tx = ''.join([c for c in item_tx if c.isdigit()])
            if tx and item_tx != tx:
                continue
            values = self._extract_comprobante_values(item)
            if values.get('id') or values.get('nroEmision'):
                return values
        return {'id': False, 'nroEmision': False, 'observacion': False}

    @api.model
    def _recover_comprobante_from_logs(self, retention_line):
        record = retention_line.arba_retention_record_id
        log = (
            self.env['arba.a122r.request.log']
            .sudo()
            .search(
                [
                    ('endpoint', '=', '/external/comprobante'),
                    ('method', '=', 'POST'),
                    ('state', '=', 'ok'),
                ]
                + (
                    [('retention_record_id', '=', record.id)]
                    if record
                    else [('retention_line_id', '=', retention_line.id)]
                ),
                order='id desc',
                limit=1,
            )
        )
        if not log or not log.response_payload:
            return {'id': False, 'nroEmision': False, 'observacion': False}
        try:
            payload = json.loads(log.response_payload)
        except Exception:
            return {'id': False, 'nroEmision': False, 'observacion': False}
        return self._extract_comprobante_values(payload)

    @api.model
    def _recover_comprobante_from_api(
        self, company, retention_line, request_payload=False
    ):
        cuit_agente = self._sanitize_cuit(company.partner_id.vat)
        tx = retention_line.arba_n_transaccion_agente
        id_dj = retention_line.arba_id_dj or (request_payload or {}).get('idDj')
        cuit_contribuyente = (request_payload or {}).get('cuitContribuyente')
        anio, mes, quincena = self._get_period_values(
            company, retention_line.payment_order_id.date
        )
        attempts = []
        if id_dj:
            attempts.append({'idDj': int(id_dj)})
        attempts.append(
            {
                'cuitAgente': int(cuit_agente),
                'anio': int(anio),
                'mes': int(mes),
                'quincena': int(quincena),
            }
        )
        if cuit_contribuyente:
            attempts.append(
                {
                    'cuitAgente': int(cuit_agente),
                    'cuitContribuyente': int(cuit_contribuyente),
                    'anio': int(anio),
                    'mes': int(mes),
                    'quincena': int(quincena),
                }
            )
        for params in attempts:
            try:
                response_data = self._do_request(
                    company,
                    method='GET',
                    path='/external/comprobantes',
                    params=params,
                )
                self._create_request_log(
                    company,
                    '/external/comprobantes',
                    'GET',
                    payload=params,
                    response=response_data,
                    status_code=200,
                    payment_order=retention_line.payment_order_id,
                    retention_line=retention_line,
                )
                values = self._extract_comprobante_from_collection(
                    response_data, tx
                )
                if values.get('id') or values.get('nroEmision'):
                    return values
            except ValidationError as err:
                self._create_request_log(
                    company,
                    '/external/comprobantes',
                    'GET',
                    payload=params,
                    error_message=str(err),
                    status_code=400,
                    payment_order=retention_line.payment_order_id,
                    retention_line=retention_line,
                )
        return {'id': False, 'nroEmision': False, 'observacion': False}

    @api.model
    def _get_or_create_dj(
        self,
        company,
        date_value,
        payment_order=False,
        retention_line=False,
        actividad_id=False,
    ):
        cuit_agente = self._sanitize_cuit(company.partner_id.vat)
        anio, mes, quincena = self._get_period_values(company, date_value)
        actividad_id = int(
            actividad_id or company._get_default_arba_a122r_activity_code()
        )
        DjCache = self.env['arba.a122r.dj']
        cache = DjCache.search(
            [
                ('company_id', '=', company.id),
                ('cuit_agente', '=', cuit_agente),
                ('actividad_id', '=', actividad_id),
                ('anio', '=', anio),
                ('mes', '=', mes),
                ('quincena', '=', quincena),
            ],
            limit=1,
        )
        if cache and cache.arba_id_dj:
            if not cache.activity_line_id:
                activity_line = DjCache._find_company_activity_line(
                    company, actividad_id
                )
                if activity_line:
                    cache.write({'activity_line_id': activity_line.id})
            return cache

        payload = {
            'cuitAgente': int(cuit_agente),
            'actividadId': actividad_id,
            'anio': anio,
            'mes': mes,
            'quincena': quincena,
        }
        arba_id_dj = False
        post_error = False

        def _is_network_error(message):
            text = (message or '').lower()
            return (
                'tiempo de espera agotado' in text
                or 'no se pudo conectar con arba a122r' in text
            )

        try:
            response_data = self._do_request(
                company,
                method='POST',
                path='/external/declaracionJurada',
                payload=payload,
            )
            self._create_request_log(
                company,
                '/external/declaracionJurada',
                'POST',
                payload=payload,
                response=response_data,
                status_code=200,
                payment_order=payment_order,
                retention_line=retention_line,
            )
            arba_id_dj = self._extract_dj_id(response_data)
        except ValidationError as err:
            # ARBA can return 400 with a business message indicating the DJ already exists.
            # In that case, the message usually includes "DDJJ Id: <id>".
            post_error = err
            self._create_request_log(
                company,
                '/external/declaracionJurada',
                'POST',
                payload=payload,
                error_message=str(err),
                status_code=400,
                payment_order=payment_order,
                retention_line=retention_line,
            )
            if _is_network_error(str(err)):
                raise
            if quincena == 0 and 'Fecha de vencimiento no encontrada' in str(
                err
            ):
                raise UserError(
                    _(
                        'ARBA rechazó la DJ para período mensual. '
                        'Configure la periodicidad "Quincenal" en la compañía y reintente.\n'
                        'Detalle ARBA: %s'
                    )
                    % str(err)
                ) from err
            arba_id_dj = self._extract_dj_id_from_error(str(err))
        if not arba_id_dj:
            try:
                response_data = self._do_request(
                    company,
                    method='GET',
                    path='/external/declaracionJurada',
                    params=payload,
                )
                self._create_request_log(
                    company,
                    '/external/declaracionJurada',
                    'GET',
                    payload=payload,
                    response=response_data,
                    status_code=200,
                    payment_order=payment_order,
                    retention_line=retention_line,
                )
                arba_id_dj = self._extract_dj_id(response_data)
            except ValidationError as get_err:
                self._create_request_log(
                    company,
                    '/external/declaracionJurada',
                    'GET',
                    payload=payload,
                    error_message=str(get_err),
                    status_code=400,
                    payment_order=payment_order,
                    retention_line=retention_line,
                )
                if post_error:
                    raise post_error
                raise

        if not arba_id_dj:
            if post_error:
                raise post_error
            raise ValidationError(
                _('No se pudo resolver el ID de DJ ARBA para el período.')
            )

        activity_line = DjCache._find_company_activity_line(
            company, actividad_id
        )
        vals = {
            'company_id': company.id,
            'cuit_agente': cuit_agente,
            'actividad_id': actividad_id,
            'activity_line_id': activity_line.id or False,
            'anio': anio,
            'mes': mes,
            'quincena': quincena,
            'arba_id_dj': int(arba_id_dj),
            'last_sync': fields.Datetime.now(),
        }
        if cache:
            cache.write(vals)
            return cache
        return DjCache.create(vals)

    @api.model
    def _find_dj_cache(self, company, date_value, actividad_id):
        cuit_agente = self._sanitize_cuit(company.partner_id.vat)
        anio, mes, quincena = self._get_period_values(company, date_value)
        return self.env['arba.a122r.dj'].search(
            [
                ('company_id', '=', company.id),
                ('cuit_agente', '=', cuit_agente),
                ('actividad_id', '=', int(actividad_id)),
                ('anio', '=', anio),
                ('mes', '=', mes),
                ('quincena', '=', quincena),
            ],
            limit=1,
        )

    @api.model
    def _resolve_activity_for_line(self, retention_line):
        company = retention_line.payment_order_id.company_id
        company._ensure_arba_a122r_activity_defaults()
        configured_codes = {
            int(item.activity_code) for item in company.arba_a122r_activity_ids
        }
        default_code = company._get_default_arba_a122r_activity_code()
        partner = (
            retention_line.partner_id
            or retention_line.payment_order_id.partner_id
        )
        partner_activity_code = False
        if (
            partner
            and partner.retention_activity_id
            and partner.retention_activity_id.code
        ):
            digits = ''.join(
                [
                    c
                    for c in str(partner.retention_activity_id.code)
                    if c.isdigit()
                ]
            )
            if digits:
                partner_activity_code = int(digits)
            else:
                raise UserError(
                    _(
                        'La actividad de retención del proveedor %(partner)s no '
                        'tiene un código numérico válido (%(code)s). Corrija el '
                        'código de actividad del partner para informar por A122R.',
                        partner=partner.display_name,
                        code=partner.retention_activity_id.code,
                    )
                )

        if not partner_activity_code:
            if default_code:
                return int(default_code)
            raise UserError(
                _(
                    'No hay actividad ARBA A122R resoluble para la compañía. '
                    'Configure una actividad habitual.'
                )
            )

        if partner_activity_code not in configured_codes:
            raise UserError(
                _(
                    'El proveedor %(partner)s tiene actividad %(activity)s, pero '
                    'la compañía no la tiene habilitada para A122R.\nRevise la '
                    'actividad del partner o agregue esa actividad en la '
                    'configuración A122R de la compañía.',
                    partner=partner.display_name,
                    activity=partner_activity_code,
                )
            )
        return partner_activity_code

    @api.model
    def _prepare_payload(self, retention_line, dj_id):
        company = retention_line.payment_order_id.company_id
        partner = (
            retention_line.partner_id
            or retention_line.payment_order_id.partner_id
        )
        if not partner:
            raise ValidationError(
                _(
                    'Falta el partner en la línea de retención %(line)s. '
                    'No se puede armar el payload ARBA A122R.',
                    line=retention_line.id,
                )
            )
        if not partner.vat:
            raise ValidationError(
                _(
                    'Falta CUIT del partner %(partner)s en la línea de retención %(line)s.',
                    partner=partner.display_name,
                    line=retention_line.id,
                )
            )
        cuit_agente = self._sanitize_cuit(company.partner_id.vat)
        cuit_contribuyente = self._sanitize_cuit(partner.vat)
        retention_line.arba_n_transaccion_agente = (
            self._normalize_transaction_number(retention_line)
        )
        if not retention_line.arba_fecha_operacion:
            retention_line.arba_fecha_operacion = (
                retention_line.payment_order_id.date
            )

        base_amount = round(retention_line.base, 2)
        amount = round(retention_line.amount, 2)
        # ARBA validates internal consistency: derive aliquot from effective
        # base/amount used on the retention line, and only fallback to taxapp
        # when there is no base amount.
        alicuota = 0.0
        if base_amount:
            alicuota = round(abs(amount / base_amount) * 100, 2)
        elif retention_line.taxapp_id:
            alicuota = round(abs(retention_line.taxapp_id.percent), 2)

        payload = {
            'idDj': int(dj_id),
            'cuitContribuyente': int(cuit_contribuyente),
            'cuitAgente': int(cuit_agente),
            'sucursal': str(company.arba_a122r_sucursal),
            'alicuota': alicuota,
            'baseImponible': base_amount,
            'importeRetencion': amount,
            'razonSocialContribuyente': (partner.name or '')[:50],
            'fechaOperacion': self._iso_datetime_from_date(
                retention_line.arba_fecha_operacion
            ),
            'nTransaccionAgente': retention_line.arba_n_transaccion_agente,
        }
        direccion = {
            'calle': (partner.street or '')[:50],
            'numero': (partner.num or '')[:5],
            'piso': (partner.floor or '')[:5],
            'departamento': (partner.apartment or '')[:5],
            'codigoPostal': (partner.zip or '')[:8],
            'localidad': (partner.city or '')[:32],
            'provincia': (partner.state_id.name or '')[:32],
        }
        if any(direccion.values()):
            payload['direccion'] = direccion
        return payload

    @api.model
    def sync_retention_line(  # noqa: C901
        self, retention_line, raise_on_error=False
    ):
        line = retention_line
        if not line._is_arba_retention_syncable():
            return False

        company = line.payment_order_id.company_id
        record = self._get_or_create_retention_record(line)
        if (
            line.arba_sync_state in ('sent', 'observed')
            or line.arba_id_comprobante
            or record.arba_sync_state in ('sent', 'observed')
            or record.arba_id_comprobante
        ):
            self._sync_line_from_record(record, line)
            return True
        stage = 'dj'
        try:
            if line.arba_sync_state == 'deleted':
                # Luego de una baja en ARBA, el reenvío debe usar un nuevo número
                # de transacción para evitar el rechazo por duplicado.
                line.arba_n_transaccion_agente = self._next_transaction_number(
                    line
                )
            actividad_id = self._resolve_activity_for_line(line)
            existing_dj = self._find_dj_cache(
                company, line.payment_order_id.date, actividad_id
            )
            if existing_dj and existing_dj.state == 'closed':
                raise UserError(
                    _(
                        'La DJ %(dj)s del período %(period)s y actividad %(activity)s está cerrada en Odoo. '
                        'Reabrila o use otra DJ para informar nuevas retenciones.',
                        dj=existing_dj.arba_id_dj or '-',
                        period='%s/%s-Q%s'
                        % (
                            existing_dj.anio,
                            str(existing_dj.mes).zfill(2),
                            existing_dj.quincena,
                        ),
                        activity=existing_dj.actividad_id,
                    )
                )
            dj_cache = self._get_or_create_dj(
                company,
                line.payment_order_id.date,
                payment_order=line.payment_order_id,
                retention_line=line,
                actividad_id=actividad_id,
            )
            payload = self._prepare_payload(line, dj_cache.arba_id_dj)
            pending_vals = {
                'arba_sync_state': 'pending',
                'arba_id_dj': dj_cache.arba_id_dj,
                'arba_actividad_id_used': actividad_id,
                'arba_last_request': json.dumps(
                    payload, ensure_ascii=True, sort_keys=True
                ),
                'arba_last_error': False,
                'arba_last_response': False,
                'arba_observacion': False,
                'arba_fecha_operacion': line.arba_fecha_operacion,
                'arba_n_transaccion_agente': line.arba_n_transaccion_agente,
            }
            record.sudo().write(
                dict(
                    self._build_record_snapshot_from_line(
                        line, payload=payload
                    ),
                    **pending_vals
                )
            )
            self._sync_line_from_record(record, line)
            stage = 'comprobante'
            response_data = self._do_request(
                company,
                method='POST',
                path='/external/comprobante',
                payload=payload,
            )
            self._create_request_log(
                company,
                '/external/comprobante',
                'POST',
                payload=payload,
                response=response_data,
                status_code=200,
                payment_order=line.payment_order_id,
                retention_record=record,
                retention_line=line,
            )
            values = self._extract_comprobante_values(response_data)
            state = 'observed' if values['observacion'] else 'sent'
            record.sudo().write(
                {
                    'arba_sync_state': state,
                    'arba_id_comprobante': values['id'] or False,
                    'arba_nro_emision': values['nroEmision'] or False,
                    'arba_observacion': values['observacion'] or False,
                    'arba_last_response': (
                        json.dumps(
                            response_data, ensure_ascii=True, sort_keys=True
                        )
                        if isinstance(response_data, (dict, list))
                        else str(response_data)
                    ),
                    'arba_last_error': False,
                    'current_retention_line_id': line.id,
                    'lifecycle_state': 'linked',
                    'current': True,
                }
            )
            self._sync_line_from_record(record, line)
            if record.arba_id_comprobante:
                try:
                    self.get_comprobante_pdf_from_record(
                        record, force_refresh=True
                    )
                except Exception:
                    _logger.warning(
                        'No se pudo cachear el PDF ARBA de la línea %s luego del envío.',
                        line.id,
                    )
            self._create_comprobante_history(
                line,
                record,
                action='send',
                state=state,
                notes=values['observacion'] or False,
            )
            return True
        except Exception as err:
            _logger.exception(
                'ARBA A122R sync failed for retention line %s', line.id
            )
            error_message = str(err)
            if 'Número de transacción ya existente' in error_message:
                recovered = self._recover_comprobante_from_logs(line)
                if not recovered.get('id'):
                    recovered = self._recover_comprobante_from_api(
                        company,
                        line,
                        request_payload=(
                            payload if 'payload' in locals() else False
                        ),
                    )
                record.sudo().write(
                    {
                        'arba_sync_state': 'sent',
                        'arba_id_comprobante': recovered['id']
                        or record.arba_id_comprobante
                        or False,
                        'arba_nro_emision': recovered['nroEmision']
                        or record.arba_nro_emision
                        or False,
                        'arba_observacion': recovered['observacion']
                        or _(
                            'ARBA indicó que la transacción ya fue informada para el período.'
                        ),
                        'arba_last_error': False,
                    }
                )
                self._sync_line_from_record(record, line)
                self._create_comprobante_history(
                    line,
                    record,
                    action='send',
                    state='sent',
                    notes=_(
                        'Reenvío omitido: ARBA indicó que la transacción ya fue informada.'
                    ),
                )
                if record.arba_id_comprobante:
                    try:
                        self.get_comprobante_pdf_from_record(
                            record, force_refresh=False
                        )
                    except Exception:
                        _logger.warning(
                            'No se pudo recuperar/cachear el PDF ARBA de la línea %s.',
                            line.id,
                        )
                if stage == 'comprobante':
                    self._create_request_log(
                        company,
                        '/external/comprobante',
                        'POST',
                        payload=payload if 'payload' in locals() else False,
                        error_message=error_message,
                        status_code=400,
                        payment_order=line.payment_order_id,
                        retention_record=record,
                        retention_line=line,
                    )
                return True
            if stage == 'comprobante':
                self._create_request_log(
                    company,
                    '/external/comprobante',
                    'POST',
                    payload=payload if 'payload' in locals() else False,
                    error_message=error_message,
                    status_code=400,
                    payment_order=line.payment_order_id,
                    retention_record=record,
                    retention_line=line,
                )
            record.sudo().write(
                {
                    'arba_sync_state': 'error',
                    'arba_last_error': error_message,
                }
            )
            self._sync_line_from_record(record, line)
            payment = line.payment_order_id
            if payment:
                payment.message_post(
                    body=_(
                        'Error de sincronización ARBA A122R en línea %(line)s: %(error)s',
                        line=line.id,
                        error=error_message,
                    )
                )
            if raise_on_error:
                raise
            return False

    @api.model
    def delete_remote_comprobante(self, retention_line):
        line = retention_line
        record = self._ensure_record_snapshot_from_line(
            line, line.arba_retention_record_id
        )
        if not record.arba_id_comprobante:
            raise ValidationError(
                _('Esta línea de retención no tiene ID de comprobante ARBA.')
            )
        previous_values = {
            'arba_id_comprobante': record.arba_id_comprobante,
            'arba_nro_emision': record.arba_nro_emision,
            'arba_n_transaccion_agente': record.arba_n_transaccion_agente,
            'arba_id_dj': record.arba_id_dj,
        }
        endpoint = '/external/comprobante/%s' % record.arba_id_comprobante
        try:
            response_data = self._do_request(
                line.payment_order_id.company_id,
                method='DELETE',
                path=endpoint,
            )
        except ValidationError as err:
            error_text = str(err)
            self._create_request_log(
                line.payment_order_id.company_id,
                endpoint,
                'DELETE',
                error_message=error_text,
                status_code=400,
                payment_order=line.payment_order_id,
                retention_record=record,
                retention_line=line,
            )
            if 'Comprobante ya fue borrado' not in error_text:
                raise
            response_data = {
                'estado': 'ok',
                'detalle': 'Comprobante ya borrado en ARBA',
            }
        self._create_request_log(
            line.payment_order_id.company_id,
            endpoint,
            'DELETE',
            response=response_data,
            status_code=200,
            payment_order=line.payment_order_id,
            retention_record=record,
            retention_line=line,
        )
        record.sudo().write(
            {
                'arba_sync_state': 'deleted',
                'arba_last_response': (
                    json.dumps(response_data, ensure_ascii=True)
                    if isinstance(response_data, (dict, list))
                    else str(response_data)
                ),
            }
        )
        self._sync_line_from_record(record, line)
        try:
            # Refresh cached PDF so it reflects "dado de baja" status from ARBA.
            self.get_comprobante_pdf_from_record(record, force_refresh=True)
        except Exception:
            _logger.warning(
                'No se pudo refrescar el PDF ARBA de la línea %s luego de la baja.',
                line.id,
            )
        history = (
            self.env['arba.a122r.comprobante.history']
            .sudo()
            .create(
                {
                    'retention_record_id': record.id,
                    'retention_line_id': line.id,
                    'payment_order_id': line.payment_order_id.id,
                    'company_id': line.payment_order_id.company_id.id,
                    'action': 'delete',
                    'state': 'deleted',
                    'arba_id_dj': previous_values['arba_id_dj'] or 0,
                    'arba_id_comprobante': previous_values[
                        'arba_id_comprobante'
                    ]
                    or 0,
                    'arba_nro_emision': previous_values['arba_nro_emision']
                    or False,
                    'arba_n_transaccion_agente': previous_values[
                        'arba_n_transaccion_agente'
                    ]
                    or False,
                    'notes': (
                        'ARBA indicó que el comprobante ya estaba dado de baja.'
                        if isinstance(response_data, dict)
                        and response_data.get('detalle')
                        == 'Comprobante ya borrado en ARBA'
                        else False
                    ),
                }
            )
        )
        record.sudo().write({'current_history_entry_id': history.id})
        return True

    @api.model
    def get_comprobante_pdf(self, retention_line, force_refresh=False):
        line = retention_line
        record = self._ensure_record_snapshot_from_line(
            line, line.arba_retention_record_id
        )
        attachment = self.get_comprobante_pdf_from_record(
            record, force_refresh=force_refresh
        )
        if attachment and line.arba_pdf_attachment_id != attachment:
            line.sudo().write({'arba_pdf_attachment_id': attachment.id})
        return base64.b64decode(attachment.datas)

    @api.model
    def get_comprobante_pdf_from_record(
        self, retention_record, force_refresh=False
    ):
        record = retention_record
        if not record.arba_id_comprobante:
            raise ValidationError(
                _('Este registro persistente no tiene ID de comprobante ARBA.')
            )
        if not force_refresh:
            cached_pdf = self._get_cached_comprobante_pdf(record)
            if cached_pdf:
                return record.arba_pdf_attachment_id
        response = self._do_request(
            record.company_id,
            method='GET',
            path='/external/comprobantePdf',
            params={'id': int(record.arba_id_comprobante)},
        )
        self._create_request_log(
            record.company_id,
            '/external/comprobantePdf',
            'GET',
            payload={'id': int(record.arba_id_comprobante)},
            response='binary/pdf' if isinstance(response, bytes) else response,
            status_code=200,
            payment_order=record.payment_order_id,
            retention_record=record,
            retention_line=record.current_retention_line_id,
        )
        pdf_data = self._extract_pdf_bytes(response)
        return self._store_comprobante_pdf_attachment(record, pdf_data)


class AccountPaymentOrder(models.Model):
    _inherit = 'account.payment.order'

    arba_a122r_request_log_ids = fields.One2many(
        comodel_name='arba.a122r.request.log',
        inverse_name='payment_order_id',
        string='Solicitudes ARBA A122R',
        readonly=True,
    )
    has_arba_digital_retentions = fields.Boolean(
        compute='_compute_has_arba_digital_retentions'
    )
    has_active_arba_retentions = fields.Boolean(
        compute='_compute_has_active_arba_retentions'
    )
    arba_retention_record_ids = fields.One2many(
        'arba.a122r.retention.record',
        'payment_order_id',
        string='Registros persistentes ARBA',
        readonly=True,
    )
    arba_retention_record_count = fields.Integer(
        compute='_compute_arba_retention_record_stats'
    )
    has_orphaned_arba_retention_records = fields.Boolean(
        compute='_compute_arba_retention_record_stats'
    )

    @api.depends(
        'retention_ids',
        'retention_ids.is_arba_digital',
    )
    def _compute_has_arba_digital_retentions(self):
        for payment in self:
            payment.has_arba_digital_retentions = any(
                line.is_arba_digital for line in payment.retention_ids
            )

    @api.depends(
        'type',
        'retention_ids',
        'retention_ids.is_arba_digital',
        'retention_ids.arba_sync_state',
    )
    def _compute_has_active_arba_retentions(self):
        for payment in self:
            payment.has_active_arba_retentions = bool(
                payment._get_active_arba_retention_lines()
            )

    @api.depends(
        'arba_retention_record_ids',
        'arba_retention_record_ids.lifecycle_state',
    )
    def _compute_arba_retention_record_stats(self):
        for payment in self:
            payment.arba_retention_record_count = len(
                payment.arba_retention_record_ids
            )
            payment.has_orphaned_arba_retention_records = any(
                record.lifecycle_state == 'orphaned'
                for record in payment.arba_retention_record_ids
            )

    def _get_active_arba_retention_lines(self):
        self.ensure_one()
        return self.retention_ids.filtered(
            lambda line: line.is_arba_digital
            and line.arba_sync_state in ('sent', 'observed')
        )

    def _check_arba_retentions_recompute_allowed(self):
        for payment in self:
            active_lines = payment._get_active_arba_retention_lines()
            if active_lines:
                raise ValidationError(
                    _(
                        'No se pueden recalcular las retenciones porque la '
                        'orden de pago tiene retenciones ARBA ya informadas.\n'
                        'Primero debe dar de baja manualmente esas retenciones en ARBA y luego volver a editar el pago.'
                    )
                )

    def action_move_line_create(self):
        return super().action_move_line_create()

    def proforma_voucher(self):
        result = super().proforma_voucher()
        if result is not True:
            return result
        for payment in self.filtered(
            lambda p: p.type == 'payment' and p.state == 'posted'
        ):
            payment._sync_arba_retentions_after_post(
                raise_on_error=payment.company_id.arba_a122r_block_validation_on_error
            )
        return result

    def _sync_arba_retentions_after_post(self, raise_on_error=False):
        self.ensure_one()
        lines = self.retention_ids.filtered(
            lambda line: line._is_arba_retention_syncable()
            and line.arba_sync_state not in ('sent', 'observed')
            and not line.arba_id_comprobante
        )
        if not lines:
            return
        for line in lines:
            line.action_arba_send(raise_on_error=raise_on_error)

    @api.model
    def fields_view_get(
        self, view_id=None, view_type='form', toolbar=False, submenu=False
    ):
        result = super().fields_view_get(
            view_id=view_id,
            view_type=view_type,
            toolbar=toolbar,
            submenu=submenu,
        )
        if self.env.company.arba_a122r_enforced and 'toolbar' in result:
            print_actions = result.get('toolbar', {}).get('print', [])
            certificate_id = self.env.ref(
                'l10n_ar_eynes.action_print_retention_certificate_qweb'
            ).id
            result['toolbar']['print'] = [
                action
                for action in print_actions
                if action.get('id') != certificate_id
            ]
        return result


class AccountPaymentOrderRetentionLine(models.Model):
    _inherit = 'account.payment.order.retention.line'

    arba_retention_record_id = fields.Many2one(
        'arba.a122r.retention.record',
        string='Registro persistente ARBA',
        copy=False,
        readonly=True,
        ondelete='set null',
    )
    arba_sync_state = fields.Selection(
        selection=[
            ('pending', 'Pendiente'),
            ('sent', 'Informada'),
            ('observed', 'Observada'),
            ('error', 'Error'),
            ('deleted', 'Dada de baja'),
        ],
        default=False,
        copy=False,
    )
    arba_id_dj = fields.Integer(copy=False)
    arba_id_comprobante = fields.Integer(copy=False)
    arba_nro_emision = fields.Char(copy=False)
    arba_observacion = fields.Char(copy=False)
    arba_last_request = fields.Text(copy=False)
    arba_last_response = fields.Text(copy=False)
    arba_last_error = fields.Text(copy=False)
    arba_n_transaccion_agente = fields.Char(copy=False)
    arba_fecha_operacion = fields.Date(copy=False)
    arba_actividad_id_used = fields.Integer(copy=False, readonly=True)
    is_arba_digital = fields.Boolean(compute='_compute_is_arba_digital')
    payment_order_state = fields.Selection(
        related='payment_order_id.state',
        readonly=True,
        string='Estado orden de pago',
    )
    arba_history_ids = fields.One2many(
        'arba.a122r.comprobante.history',
        'retention_line_id',
        string='Historial de comprobantes ARBA',
        readonly=True,
    )
    arba_pdf_attachment_id = fields.Many2one(
        'ir.attachment',
        copy=False,
        readonly=True,
        string='PDF comprobante ARBA',
    )

    _arba_n_transaccion_agente_uniq = models.Constraint(
        'UNIQUE(arba_n_transaccion_agente)',
        'El número de transacción ARBA debe ser único.',
    )

    def _get_retention_tax(self):
        self.ensure_one()
        retention = self.retention_id
        if not retention:
            return self.env['account.tax']
        if retention._name == 'account.tax':
            return retention
        return retention.tax_id

    @api.depends('retention_id', 'retention_type')
    def _compute_is_arba_digital(self):
        for rec in self:
            tax = rec._get_retention_tax()
            rec.is_arba_digital = bool(
                tax
                and tax.retention_type == 'gross_income'
                and tax.inform_arba
                and rec.payment_order_id.type == 'payment'
            )

    def _is_arba_retention_syncable(self):
        self.ensure_one()
        tax = self._get_retention_tax()
        return bool(
            tax
            and self.payment_order_id.type == 'payment'
            and self.payment_order_id.company_id.arba_a122r_enabled
            and tax.retention_type == 'gross_income'
            and tax.inform_arba
        )

    def _get_arba_syncability_issues(self):
        self.ensure_one()
        issues = []
        tax = self._get_retention_tax()
        if self.payment_order_id.type != 'payment':
            issues.append(
                _(
                    'La orden debe ser un pago a proveedor para informar retenciones en ARBA.'
                )
            )
        if not self.payment_order_id.company_id.arba_a122r_enabled:
            issues.append(
                _('La integración ARBA A122R está desactivada en la compañía.')
            )
        if not tax:
            issues.append(
                _('La línea no tiene impuesto de retención configurado.')
            )
        else:
            if tax.retention_type != 'gross_income':
                issues.append(
                    _('Solo se pueden informar retenciones de Ingresos Brutos.')
                )
            if not tax.inform_arba:
                issues.append(
                    _(
                        'El impuesto no está marcado para informar a ARBA (campo "Inform ARBA").'
                    )
                )
        return issues

    def action_arba_send(self, raise_on_error=False):
        service = self.env['arba.a122r.service']
        ok_lines = self.env['account.payment.order.retention.line']
        already_reported_lines = self.env[
            'account.payment.order.retention.line'
        ]
        error_lines = self.env['account.payment.order.retention.line']
        skipped = []
        for line in self:
            if line.payment_order_id.state != 'posted':
                raise UserError(
                    _(
                        'Solo se puede informar una retención ARBA cuando la orden de pago ya fue validada.'
                    )
                )
            issues = line._get_arba_syncability_issues()
            if issues:
                skipped.append(
                    _('No se pudo informar la línea %(line)s: %(issues)s')
                    % {
                        'line': line.id,
                        'issues': '; '.join(issues),
                    }
                )
                continue
            ok = service.sync_retention_line(
                line, raise_on_error=raise_on_error
            )
            if ok:
                ok_lines |= line
                if (line.arba_observacion or '').lower().find(
                    'ya fue informada'
                ) >= 0:
                    already_reported_lines |= line
            else:
                error_lines |= line

        if raise_on_error and error_lines:
            raise ValidationError(
                _(
                    'Falló la sincronización ARBA A122R para las líneas: %s',
                    ', '.join(str(line.id) for line in error_lines),
                )
            )

        if self.env.context.get('params'):
            if error_lines:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('ARBA A122R'),
                        'message': _(
                            'Se procesaron %(total)s línea(s): %(ok)s OK, '
                            '%(error)s con error. Revisá el Log ARBA A122R.',
                            total=len(self),
                            ok=len(ok_lines),
                            error=len(error_lines),
                        ),
                        'type': 'warning',
                        'sticky': True,
                    },
                }
            if skipped:
                raise UserError('\n'.join(skipped))
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('ARBA A122R'),
                    'message': _(
                        'Se procesaron %(total)s línea(s): %(sent)s informadas, '
                        '%(already)s ya informadas previamente.',
                        total=len(ok_lines),
                        sent=len(ok_lines - already_reported_lines),
                        already=len(already_reported_lines),
                    ),
                    'type': 'success',
                    'sticky': False,
                },
            }
        return True

    def action_arba_delete_remote(self):
        self.ensure_one()
        self.env['arba.a122r.service'].delete_remote_comprobante(self)
        return True

    def action_arba_download_pdf(self):
        self.ensure_one()
        service = self.env['arba.a122r.service']
        force_refresh = self.arba_sync_state == 'deleted'
        service.get_comprobante_pdf(self, force_refresh=force_refresh)
        attachment = self.arba_pdf_attachment_id
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'self',
        }

    def action_open_arba_retention_record(self):
        self.ensure_one()
        if not self.arba_retention_record_id:
            self.env['arba.a122r.service']._ensure_record_snapshot_from_line(
                self
            )
        return {
            'type': 'ir.actions.act_window',
            'name': _('Registro persistente ARBA'),
            'res_model': 'arba.a122r.retention.record',
            'res_id': self.arba_retention_record_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def unlink(self):
        service = self.env['arba.a122r.service']
        service.orphan_retention_records(
            self.filtered('arba_retention_record_id')
        )
        return super().unlink()


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _render_qweb_pdf(self, report_ref, res_ids=None, data=None):
        report = self._get_report(report_ref)
        report.ensure_one()
        handled_reports = {
            'l10n_ar_eynes.report_arba_a122r_cached_pdf',
            'l10n_ar_eynes.report_arba_a122r_payment_order_cached_pdf',
            'l10n_ar_eynes.report_arba_a122r_record_cached_pdf',
        }
        if report.report_name not in handled_reports:
            return super()._render_qweb_pdf(
                report_ref, res_ids=res_ids, data=data
            )

        res_ids = res_ids or self.env.context.get('active_ids') or []
        if (
            report.report_name
            == 'l10n_ar_eynes.report_arba_a122r_record_cached_pdf'
        ):
            records = self.env['arba.a122r.retention.record'].browse(res_ids)
            if not records:
                raise UserError(
                    _('No hay registros persistentes ARBA para imprimir.')
                )
            service = self.env['arba.a122r.service']
            streams = []
            for record in records:
                if not record.arba_id_comprobante:
                    raise UserError(
                        _(
                            'El registro %(record)s no tiene comprobante ARBA informado para imprimir.',
                            record=record.display_name,
                        )
                    )
                force_refresh = record.arba_sync_state == 'deleted'
                attachment = service.get_comprobante_pdf_from_record(
                    record, force_refresh=force_refresh
                )
                streams.append(io.BytesIO(base64.b64decode(attachment.datas)))
            if len(streams) == 1:
                return streams[0].getvalue(), 'pdf'
            return report._merge_pdfs(streams), 'pdf'
        if (
            report.report_name
            == 'l10n_ar_eynes.report_arba_a122r_payment_order_cached_pdf'
        ):
            orders = self.env['account.payment.order'].browse(res_ids)
            lines = orders.mapped('retention_ids').filtered(
                lambda line: line.is_arba_digital and line.arba_id_comprobante
            )
            if not lines:
                raise UserError(
                    _(
                        'La orden de pago no tiene retenciones ARBA informadas para imprimir.'
                    )
                )
        else:
            lines = self.env['account.payment.order.retention.line'].browse(
                res_ids
            )
        if not lines:
            raise UserError(_('No hay líneas de retención para imprimir.'))

        service = self.env['arba.a122r.service']
        streams = []
        for line in lines:
            if not line.arba_id_comprobante:
                raise UserError(
                    _(
                        'La línea %s no tiene comprobante ARBA informado para imprimir.',
                        line.display_name or line.id,
                    )
                )
            force_refresh = line.arba_sync_state == 'deleted'
            pdf_data = service.get_comprobante_pdf(
                line, force_refresh=force_refresh
            )
            streams.append(io.BytesIO(pdf_data))

        if len(streams) == 1:
            return streams[0].getvalue(), 'pdf'
        return report._merge_pdfs(streams), 'pdf'
