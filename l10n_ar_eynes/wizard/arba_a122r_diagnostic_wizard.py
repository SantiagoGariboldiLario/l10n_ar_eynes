import calendar
import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ArbaA122rDiagnosticWizard(models.TransientModel):
    _name = 'arba.a122r.diagnostic.wizard'
    _description = 'Asistente de diagnóstico ARBA A122R'

    company_id = fields.Many2one(
        'res.company',
        required=True,
        default=lambda self: self.env.company,
        string='Compañía',
    )
    company_id_domain = fields.Char(
        default=lambda self: self._default_company_ids()
    )
    activity_line_id = fields.Many2one(
        'res.company.arba.a122r.activity',
        required=True,
        string='Actividad',
        domain="[('company_id', '=', company_id)]",
    )
    anio = fields.Integer(
        required=True, default=lambda self: fields.Date.today().year
    )
    mes = fields.Integer(
        required=True, default=lambda self: fields.Date.today().month
    )
    quincena = fields.Selection(
        [('0', 'Mensual'), ('1', '1ra quincena'), ('2', '2da quincena')],
        required=True,
        default='1',
        string='Quincena',
    )
    remote_state = fields.Char(
        string='Estado remoto (opcional)',
        help='Valor opcional para filtrar por estado en ARBA (ej: ACTIVO).',
    )
    result_line_ids = fields.One2many(
        'arba.a122r.diagnostic.line',
        'wizard_id',
        string='Resultados',
        readonly=True,
    )
    matched_count = fields.Integer(string='Matcheadas', readonly=True)
    only_remote_count = fields.Integer(string='Solo remotas', readonly=True)
    only_local_count = fields.Integer(string='Solo locales', readonly=True)
    conflict_count = fields.Integer(string='Conflictos', readonly=True)
    execution_date = fields.Datetime(string='Última ejecución', readonly=True)
    applied_date = fields.Datetime(string='Última aplicación', readonly=True)

    @api.model
    def _default_company_ids(self):
        return json.dumps(
            [('id', 'in', self.env.context.get('allowed_company_ids', []))]
        )

    @api.onchange('company_id')
    def _onchange_company_id_defaults(self):
        for wizard in self:
            if not wizard.company_id:
                continue
            default_activity = (
                wizard.company_id.arba_a122r_activity_ids.filtered(
                    lambda a: a.is_default
                )[:1]
            )
            wizard.activity_line_id = default_activity
            wizard.quincena = (
                '0'
                if wizard.company_id.arba_a122r_quincena_mode == 'monthly'
                else '1'
            )

    @api.constrains('mes')
    def _check_mes(self):
        for wizard in self:
            if wizard.mes < 1 or wizard.mes > 12:
                raise ValidationError(_('El mes debe estar entre 1 y 12.'))

    @api.constrains('quincena', 'company_id')
    def _check_quincena_company_mode(self):
        for wizard in self:
            if not wizard.company_id:
                continue
            if (
                wizard.company_id.arba_a122r_quincena_mode == 'monthly'
                and wizard.quincena != '0'
            ):
                raise ValidationError(
                    _(
                        'La compañía está en modo mensual. La quincena debe ser Mensual.'
                    )
                )
            if (
                wizard.company_id.arba_a122r_quincena_mode == 'biweekly'
                and wizard.quincena
                not in (
                    '1',
                    '2',
                )
            ):
                raise ValidationError(
                    _(
                        'La compañía está en modo quincenal. La quincena debe ser 1ra o 2da.'
                    )
                )

    @api.model
    def _normalize_transaction(self, value):
        return ''.join([c for c in str(value or '') if c.isdigit()])

    def _get_period_date_range(self):
        self.ensure_one()
        start_date = fields.Date.from_string(
            '%04d-%02d-01' % (self.anio, self.mes)
        )
        last_day = calendar.monthrange(self.anio, self.mes)[1]
        end_date = fields.Date.from_string(
            '%04d-%02d-%02d' % (self.anio, self.mes, last_day)
        )
        if self.quincena == '1':
            end_date = fields.Date.from_string(
                '%04d-%02d-15' % (self.anio, self.mes)
            )
        elif self.quincena == '2':
            start_date = fields.Date.from_string(
                '%04d-%02d-16' % (self.anio, self.mes)
            )
        return start_date, end_date

    def _build_local_candidates(self, service, selected_activity):
        self.ensure_one()
        start_date, end_date = self._get_period_date_range()
        domain = [
            ('payment_order_id.company_id', '=', self.company_id.id),
            ('payment_order_id.type', '=', 'payment'),
            ('payment_order_id.date', '>=', start_date),
            ('payment_order_id.date', '<=', end_date),
            ('retention_id.tax_id.retention_type', '=', 'gross_income'),
            ('retention_id.tax_id.inform_arba', '=', True),
        ]
        local_lines = self.env['account.payment.order.retention.line'].search(
            domain
        )
        local_by_tx = {}
        local_without_tx = []
        base_conflicts = []
        for line in local_lines:
            try:
                activity = service._resolve_activity_for_line(line)
            except Exception as err:
                base_conflicts.append(
                    {
                        'diagnostic_state': 'conflict',
                        'local_line_id': line.id,
                        'n_transaccion_agente': self._normalize_transaction(
                            line.arba_n_transaccion_agente
                        ),
                        'local_sync_state': line.arba_sync_state or False,
                        'note': _(
                            'No se pudo resolver actividad para la línea local: %s',
                            str(err),
                        ),
                    }
                )
                continue
            if int(activity) != int(selected_activity):
                continue
            tx = self._normalize_transaction(line.arba_n_transaccion_agente)
            if not tx:
                local_without_tx.append(line)
                continue
            local_by_tx.setdefault(tx, []).append(line)
        return local_by_tx, local_without_tx, base_conflicts

    def _normalize_remote_items(self, remote_response):
        if isinstance(remote_response, dict):
            return [remote_response]
        if isinstance(remote_response, list):
            return remote_response
        return []

    def _build_remote_index_by_id(self, remote_items):
        remote_by_id = {}
        for item in remote_items:
            item_id = item.get('id')
            if not item_id:
                continue
            remote_by_id.setdefault(int(item_id), []).append(item)
        return remote_by_id

    def action_run_diagnostic(self):  # noqa: C901
        self.ensure_one()
        self.company_id._ensure_arba_a122r_activity_defaults()
        if not self.company_id.arba_a122r_enabled:
            raise UserError(
                _('La compañía no tiene habilitada la integración ARBA A122R.')
            )
        if not self.activity_line_id:
            raise UserError(
                _(
                    'Debe seleccionar una actividad para ejecutar el diagnóstico.'
                )
            )

        service = self.env['arba.a122r.service']
        selected_activity = int(self.activity_line_id.activity_code)
        cuit_agente = service._sanitize_cuit(self.company_id.partner_id.vat)
        quincena = int(self.quincena)

        dj_params = {
            'cuitAgente': int(cuit_agente),
            'actividadId': selected_activity,
            'anio': int(self.anio),
            'mes': int(self.mes),
            'quincena': quincena,
        }
        try:
            dj_response = service._do_request(
                self.company_id,
                method='GET',
                path='/external/declaracionJurada',
                params=dj_params,
            )
            service._create_request_log(
                self.company_id,
                '/external/declaracionJurada',
                'GET',
                payload=dj_params,
                response=dj_response,
                status_code=200,
            )
        except ValidationError as err:
            raise UserError(
                _(
                    'No se pudo consultar la DJ remota para el período seleccionado.\nDetalle: %s'
                )
                % str(err)
            ) from err
        remote_dj_id = service._extract_dj_id(dj_response)

        remote_params = {
            'cuitAgente': int(cuit_agente),
            'anio': int(self.anio),
            'mes': int(self.mes),
            'quincena': quincena,
        }
        if remote_dj_id:
            remote_params['idDj'] = int(remote_dj_id)
        if self.remote_state:
            remote_params['estado'] = self.remote_state

        try:
            remote_response = service._do_request(
                self.company_id,
                method='GET',
                path='/external/comprobantes',
                params=remote_params,
            )
            service._create_request_log(
                self.company_id,
                '/external/comprobantes',
                'GET',
                payload=remote_params,
                response=remote_response,
                status_code=200,
            )
        except ValidationError as err:
            raise UserError(
                _(
                    'No se pudieron consultar los comprobantes remotos para el período seleccionado.\nDetalle: %s'
                )
                % str(err)
            ) from err

        remote_items = self._normalize_remote_items(remote_response)
        remote_by_id = self._build_remote_index_by_id(remote_items)
        (
            local_by_tx,
            local_without_tx,
            result_vals,
        ) = self._build_local_candidates(service, selected_activity)
        remote_by_tx = {}

        for item in remote_items:
            tx = self._normalize_transaction(
                item.get('nroTransaccionAgente')
                or item.get('nTransaccionAgente')
                or item.get('ntransaccionAgente')
            )
            if not tx:
                result_vals.append(
                    {
                        'diagnostic_state': 'conflict',
                        'n_transaccion_agente': False,
                        'arba_id_dj': item.get('ddjjId')
                        or remote_dj_id
                        or False,
                        'arba_id_comprobante': item.get('id') or False,
                        'arba_nro_emision': item.get('nroEmision') or False,
                        'remote_payload': json.dumps(
                            item, ensure_ascii=True, sort_keys=True
                        ),
                        'note': _(
                            'Comprobante remoto sin nTransaccionAgente. No se puede matchear en modo conservador.'
                        ),
                    }
                )
                continue
            remote_by_tx.setdefault(tx, []).append(item)

        for line in local_without_tx:
            if line.arba_id_comprobante and remote_by_id.get(
                int(line.arba_id_comprobante)
            ):
                remote_candidates = remote_by_id[int(line.arba_id_comprobante)]
                if len(remote_candidates) == 1:
                    remote_item = remote_candidates[0]
                    result_vals.append(
                        {
                            'diagnostic_state': 'matched',
                            'local_line_id': line.id,
                            'n_transaccion_agente': self._normalize_transaction(
                                remote_item.get('nroTransaccionAgente')
                                or remote_item.get('nTransaccionAgente')
                                or remote_item.get('ntransaccionAgente')
                            ),
                            'local_sync_state': line.arba_sync_state or False,
                            'arba_id_dj': remote_item.get('ddjjId')
                            or remote_dj_id
                            or False,
                            'arba_id_comprobante': remote_item.get('id')
                            or False,
                            'arba_nro_emision': remote_item.get('nroEmision')
                            or False,
                            'remote_payload': json.dumps(
                                remote_item, ensure_ascii=True, sort_keys=True
                            ),
                            'note': _(
                                'Matcheada por idComprobante ARBA (sin nTransaccionAgente local).'
                            ),
                        }
                    )
                    continue
            result_vals.append(
                {
                    'diagnostic_state': 'conflict',
                    'local_line_id': line.id,
                    'n_transaccion_agente': False,
                    'local_sync_state': line.arba_sync_state or False,
                    'note': _(
                        'La línea local no tiene nTransaccionAgente y no puede matchearse automáticamente.'
                    ),
                }
            )

        for tx in sorted(
            set(list(local_by_tx.keys()) + list(remote_by_tx.keys()))
        ):
            local_lines = local_by_tx.get(tx, [])
            remote_rows = remote_by_tx.get(tx, [])
            if local_lines and remote_rows:
                if len(local_lines) == 1 and len(remote_rows) == 1:
                    remote_item = remote_rows[0]
                    result_vals.append(
                        {
                            'diagnostic_state': 'matched',
                            'local_line_id': local_lines[0].id,
                            'n_transaccion_agente': tx,
                            'local_sync_state': local_lines[0].arba_sync_state
                            or False,
                            'arba_id_dj': remote_item.get('ddjjId')
                            or remote_dj_id
                            or False,
                            'arba_id_comprobante': remote_item.get('id')
                            or False,
                            'arba_nro_emision': remote_item.get('nroEmision')
                            or False,
                            'remote_payload': json.dumps(
                                remote_item, ensure_ascii=True, sort_keys=True
                            ),
                            'note': _(
                                'Matcheada por nTransaccionAgente exacto.'
                            ),
                        }
                    )
                    continue
                for line in local_lines:
                    result_vals.append(
                        {
                            'diagnostic_state': 'conflict',
                            'local_line_id': line.id,
                            'n_transaccion_agente': tx,
                            'local_sync_state': line.arba_sync_state or False,
                            'note': _(
                                'Conflicto: %(local)s línea(s) locales y '
                                '%(remote)s comprobante(s) remotos para la '
                                'misma transacción.',
                                local=len(local_lines),
                                remote=len(remote_rows),
                            ),
                        }
                    )
                for remote_item in remote_rows:
                    result_vals.append(
                        {
                            'diagnostic_state': 'conflict',
                            'n_transaccion_agente': tx,
                            'arba_id_dj': remote_item.get('ddjjId')
                            or remote_dj_id
                            or False,
                            'arba_id_comprobante': remote_item.get('id')
                            or False,
                            'arba_nro_emision': remote_item.get('nroEmision')
                            or False,
                            'remote_payload': json.dumps(
                                remote_item, ensure_ascii=True, sort_keys=True
                            ),
                            'note': _(
                                'Conflicto: %(local)s línea(s) locales y '
                                '%(remote)s comprobante(s) remotos para la '
                                'misma transacción.',
                                local=len(local_lines),
                                remote=len(remote_rows),
                            ),
                        }
                    )
                continue
            if local_lines:
                for line in local_lines:
                    result_vals.append(
                        {
                            'diagnostic_state': 'only_local',
                            'local_line_id': line.id,
                            'n_transaccion_agente': tx,
                            'local_sync_state': line.arba_sync_state or False,
                            'note': _(
                                'Solo existe en Odoo para este período/actividad.'
                            ),
                        }
                    )
                continue
            for remote_item in remote_rows:
                result_vals.append(
                    {
                        'diagnostic_state': 'only_remote',
                        'n_transaccion_agente': tx,
                        'arba_id_dj': remote_item.get('ddjjId')
                        or remote_dj_id
                        or False,
                        'arba_id_comprobante': remote_item.get('id') or False,
                        'arba_nro_emision': remote_item.get('nroEmision')
                        or False,
                        'remote_payload': json.dumps(
                            remote_item, ensure_ascii=True, sort_keys=True
                        ),
                        'note': _(
                            'Solo existe remoto en ARBA para este período/actividad.'
                        ),
                    }
                )

        self.result_line_ids.unlink()
        self.result_line_ids = [(0, 0, vals) for vals in result_vals]
        self._mark_heuristic_candidates()

        matched_count = len(
            self.result_line_ids.filtered(
                lambda line: line.diagnostic_state == 'matched'
            )
        )
        only_remote_count = len(
            self.result_line_ids.filtered(
                lambda line: line.diagnostic_state == 'only_remote'
            )
        )
        only_local_count = len(
            self.result_line_ids.filtered(
                lambda line: line.diagnostic_state == 'only_local'
            )
        )
        conflict_count = len(
            self.result_line_ids.filtered(
                lambda line: line.diagnostic_state == 'conflict'
            )
        )
        self.write(
            {
                'matched_count': matched_count,
                'only_remote_count': only_remote_count,
                'only_local_count': only_local_count,
                'conflict_count': conflict_count,
                'execution_date': fields.Datetime.now(),
            }
        )

        view = self.env.ref(
            'l10n_ar_eynes.arba_a122r_diagnostic_wizard_view_form'
        )
        return {
            'type': 'ir.actions.act_window',
            'name': _('Diagnóstico ARBA A122R'),
            'res_model': 'arba.a122r.diagnostic.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(view.id, 'form')],
            'target': 'new',
            'context': dict(self.env.context),
        }

    def _mark_heuristic_candidates(self):
        self.ensure_one()
        service = self.env['arba.a122r.service']
        self.result_line_ids.write(
            {
                'heuristic_candidate': False,
                'heuristic_match_key': False,
            }
        )
        local_rows = self.result_line_ids.filtered(
            lambda line: line.local_line_id
            and line.diagnostic_state in ('only_local', 'conflict')
            and not self._normalize_transaction(line.n_transaccion_agente)
        )
        remote_rows = self.result_line_ids.filtered(
            lambda line: line.diagnostic_state == 'only_remote'
            and line.remote_payload
        )
        remote_by_signature = {}
        for remote_row in remote_rows:
            payload = self._extract_remote_payload_dict(remote_row)
            signature = self._get_remote_signature(payload)
            if not signature:
                continue
            remote_by_signature.setdefault(signature, []).append(remote_row)

        consumed_remote_ids = set()
        for local_row in local_rows:
            local_line = local_row.local_line_id
            local_tx = self._normalize_transaction(
                local_line.arba_n_transaccion_agente
            )
            if not local_tx:
                id_tx = self._normalize_transaction(local_line.id)
                id_candidates = [
                    row
                    for row in remote_rows
                    if row.id not in consumed_remote_ids
                    and self._normalize_transaction(row.n_transaccion_agente)
                    == id_tx
                ]
                if len(id_candidates) == 1:
                    remote_row = id_candidates[0]
                    consumed_remote_ids.add(remote_row.id)
                    key = _('Fallback tx=id línea: %s') % id_tx
                    local_row.write(
                        {
                            'heuristic_candidate': True,
                            'heuristic_match_key': key,
                        }
                    )
                    remote_row.write(
                        {
                            'heuristic_candidate': True,
                            'heuristic_match_key': key,
                        }
                    )
                    continue

            try:
                activity = service._resolve_activity_for_line(local_line)
            except Exception:
                continue
            if int(activity) != int(self.activity_line_id.activity_code):
                continue
            signature = self._get_local_signature(service, local_line)
            candidates = [
                row
                for row in remote_by_signature.get(signature, [])
                if row.id not in consumed_remote_ids
            ]
            if len(candidates) == 1:
                remote_row = candidates[0]
                consumed_remote_ids.add(remote_row.id)
                key = _('CUIT+fecha+base+importe+alícuota')
                local_row.write(
                    {'heuristic_candidate': True, 'heuristic_match_key': key}
                )
                remote_row.write(
                    {'heuristic_candidate': True, 'heuristic_match_key': key}
                )

    def action_apply_matched(self):
        self.ensure_one()
        matched_lines = self.result_line_ids.filtered(
            lambda line: line.diagnostic_state == 'matched'
            and line.local_line_id
        )
        if not matched_lines:
            raise UserError(_('No hay líneas matcheadas para aplicar.'))

        result = self._apply_diagnostic_lines(
            matched_lines,
            notes_template=_(
                'Sincronizado desde diagnóstico ARBA A122R (match por nTransaccionAgente).'
            ),
        )
        applied = result['applied']
        skipped = result['skipped']
        conflicts = result['conflicts']

        self.applied_date = fields.Datetime.now()

        details = []
        if conflicts:
            details = conflicts[:5]
            if len(conflicts) > 5:
                details.append(
                    _('... y %s conflicto(s) más.') % (len(conflicts) - 5)
                )
        message = _(
            'Aplicación finalizada: %(applied)s línea(s) actualizada(s), %(skipped)s omitida(s).',
            applied=applied,
            skipped=skipped,
        )
        if details:
            message = '%s\n%s' % (message, '\n'.join(details))

        if self.env.context.get('params'):
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Diagnóstico ARBA A122R'),
                    'message': message,
                    'type': 'warning' if skipped else 'success',
                    'sticky': bool(skipped),
                },
            }
        return True

    def _extract_remote_payload_dict(self, diag_line):
        if not diag_line.remote_payload:
            return {}
        try:
            payload = json.loads(diag_line.remote_payload)
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    def _get_local_signature(self, service, local_line):
        partner = (
            local_line.partner_id or local_line.payment_order_id.partner_id
        )
        cuit = (
            service._sanitize_cuit(partner.vat)
            if partner and partner.vat
            else ''
        )
        fecha = fields.Date.to_date(
            local_line.arba_fecha_operacion or local_line.payment_order_id.date
        )
        base = round(float(local_line.base or 0.0), 2)
        amount = round(float(local_line.amount or 0.0), 2)
        if base:
            alicuota = round(abs(amount / base) * 100, 2)
        elif local_line.taxapp_id:
            alicuota = round(abs(float(local_line.taxapp_id.percent or 0.0)), 2)
        else:
            alicuota = 0.0
        return (
            cuit,
            fecha.strftime('%Y-%m-%d'),
            base,
            amount,
            alicuota,
        )

    def _get_remote_signature(self, remote_payload):
        if not isinstance(remote_payload, dict):
            return False
        cuit = ''.join(
            [
                c
                for c in str(remote_payload.get('cuitContribuyente') or '')
                if c.isdigit()
            ]
        )
        fecha_raw = str(remote_payload.get('fechaOperacion') or '')
        fecha = fecha_raw[:10] if len(fecha_raw) >= 10 else fecha_raw
        base = round(float(remote_payload.get('baseImponible') or 0.0), 2)
        amount = round(
            float(
                remote_payload.get('importeRetenido')
                or remote_payload.get('importeRetencion')
                or 0.0
            ),
            2,
        )
        alicuota = round(float(remote_payload.get('alicuota') or 0.0), 2)
        return (
            cuit,
            fecha,
            base,
            amount,
            alicuota,
        )

    def _apply_diagnostic_lines(self, diag_lines, notes_template):
        service = self.env['arba.a122r.service']
        applied = 0
        skipped = 0
        conflicts = []
        seen_local_line_ids = set()
        for diag_line in diag_lines:
            local_line = diag_line.local_line_id
            if local_line.id in seen_local_line_ids:
                skipped += 1
                continue
            seen_local_line_ids.add(local_line.id)
            if not local_line._is_arba_retention_syncable():
                skipped += 1
                conflicts.append(
                    _(
                        'Línea %(line)s omitida: no es elegible para ARBA A122R.',
                        line=local_line.id,
                    )
                )
                continue
            if not diag_line.arba_id_comprobante:
                skipped += 1
                conflicts.append(
                    _(
                        'Línea %(line)s omitida: la coincidencia no tiene ID de comprobante ARBA.',
                        line=local_line.id,
                    )
                )
                continue
            if local_line.arba_id_comprobante and int(
                local_line.arba_id_comprobante
            ) != int(diag_line.arba_id_comprobante):
                skipped += 1
                conflicts.append(
                    _(
                        'Línea %(line)s omitida: ya tiene ID ARBA %(current)s y la coincidencia propone %(new)s.',
                        line=local_line.id,
                        current=local_line.arba_id_comprobante,
                        new=diag_line.arba_id_comprobante,
                    )
                )
                continue

            remote_payload = self._extract_remote_payload_dict(diag_line)
            remote_observacion = (
                remote_payload.get('observacion') if remote_payload else False
            )
            remote_fecha_baja = (
                remote_payload.get('fechaBaja') if remote_payload else False
            )
            state = 'observed' if remote_observacion else 'sent'
            if remote_fecha_baja:
                state = 'deleted'

            vals = {
                'arba_sync_state': state,
                'arba_id_dj': diag_line.arba_id_dj
                or local_line.arba_id_dj
                or False,
                'arba_id_comprobante': diag_line.arba_id_comprobante,
                'arba_nro_emision': diag_line.arba_nro_emision or False,
                'arba_observacion': remote_observacion or False,
                'arba_last_response': diag_line.remote_payload or False,
                'arba_last_error': False,
            }
            local_line.write(vals)
            service._create_comprobante_history(
                local_line,
                action='send',
                state=state,
                notes=notes_template,
            )
            applied += 1
        return {'applied': applied, 'skipped': skipped, 'conflicts': conflicts}

    def action_apply_heuristic(self):  # noqa: C901
        self.ensure_one()
        service = self.env['arba.a122r.service']
        self._mark_heuristic_candidates()
        local_rows = self.result_line_ids.filtered(
            lambda line: line.local_line_id and line.heuristic_candidate
        )
        remote_rows = self.result_line_ids.filtered(
            lambda line: line.diagnostic_state == 'only_remote'
            and line.remote_payload
            and line.heuristic_candidate
        )
        if not local_rows:
            raise UserError(_('No hay candidatos heurísticos para vincular.'))

        remote_by_signature = {}
        for remote_row in remote_rows:
            payload = self._extract_remote_payload_dict(remote_row)
            signature = self._get_remote_signature(payload)
            if not signature:
                continue
            remote_by_signature.setdefault(signature, []).append(remote_row)

        heuristic_matches = self.env['arba.a122r.diagnostic.line']
        heuristic_conflicts = []
        consumed_remote_ids = set()
        for local_row in local_rows:
            local_line = local_row.local_line_id
            try:
                activity = service._resolve_activity_for_line(local_line)
            except Exception as err:
                heuristic_conflicts.append(
                    _(
                        'Línea %(line)s: no se pudo resolver actividad (%(error)s).',
                        line=local_line.id,
                        error=str(err),
                    )
                )
                continue
            if int(activity) != int(self.activity_line_id.activity_code):
                continue

            # Fallback seguro para casos legacy:
            # si la línea local no tiene nTransaccionAgente, pero existe un remoto
            # único cuyo nTransaccionAgente coincide con el id de la línea local.
            local_tx = self._normalize_transaction(
                local_line.arba_n_transaccion_agente
            )
            if not local_tx:
                id_tx = self._normalize_transaction(local_line.id)
                id_candidates = [
                    row
                    for row in remote_rows
                    if row.id not in consumed_remote_ids
                    and self._normalize_transaction(row.n_transaccion_agente)
                    == id_tx
                ]
                if len(id_candidates) == 1:
                    remote_row = id_candidates[0]
                    consumed_remote_ids.add(remote_row.id)
                    local_row.write(
                        {
                            'diagnostic_state': 'matched',
                            'arba_id_dj': remote_row.arba_id_dj,
                            'arba_id_comprobante': remote_row.arba_id_comprobante,
                            'arba_nro_emision': remote_row.arba_nro_emision,
                            'remote_payload': remote_row.remote_payload,
                            'n_transaccion_agente': id_tx,
                            'note': _(
                                'Matcheada por fallback legacy: nTransaccionAgente remoto = id de línea local.'
                            ),
                        }
                    )
                    remote_row.write(
                        {
                            'diagnostic_state': 'matched',
                            'local_line_id': local_line.id,
                            'local_sync_state': local_line.arba_sync_state,
                            'note': _(
                                'Vinculada por fallback legacy a línea local %(line)s.',
                                line=local_line.id,
                            ),
                        }
                    )
                    heuristic_matches |= local_row
                    continue
                if len(id_candidates) > 1:
                    heuristic_conflicts.append(
                        _(
                            'Línea %(line)s: hay %(count)s comprobantes remotos '
                            'con nTransaccionAgente igual al id local.',
                            line=local_line.id,
                            count=len(id_candidates),
                        )
                    )
                    continue

            signature = self._get_local_signature(service, local_line)
            candidates = [
                row
                for row in remote_by_signature.get(signature, [])
                if row.id not in consumed_remote_ids
            ]
            if len(candidates) != 1:
                if len(candidates) > 1:
                    heuristic_conflicts.append(
                        _(
                            'Línea %(line)s: hay %(count)s comprobantes remotos candidatos con la misma firma.',
                            line=local_line.id,
                            count=len(candidates),
                        )
                    )
                continue

            remote_row = candidates[0]
            consumed_remote_ids.add(remote_row.id)
            local_row.write(
                {
                    'diagnostic_state': 'matched',
                    'arba_id_dj': remote_row.arba_id_dj,
                    'arba_id_comprobante': remote_row.arba_id_comprobante,
                    'arba_nro_emision': remote_row.arba_nro_emision,
                    'remote_payload': remote_row.remote_payload,
                    'note': _('Matcheada: CUIT+fecha+base+importe+alícuota.'),
                }
            )
            remote_row.write(
                {
                    'diagnostic_state': 'matched',
                    'local_line_id': local_line.id,
                    'local_sync_state': local_line.arba_sync_state,
                    'note': _(
                        'Vinculada a línea local %(line)s.',
                        line=local_line.id,
                    ),
                }
            )
            heuristic_matches |= local_row

        if not heuristic_matches:
            raise UserError(
                _(
                    'No se encontraron coincidencias únicas por regla para aplicar.'
                )
            )

        result = self._apply_diagnostic_lines(
            heuristic_matches,
            notes_template=_(
                'Sincronizado desde diagnóstico ARBA A122R (match regla seguro).'
            ),
        )
        self.applied_date = fields.Datetime.now()
        self.matched_count = len(
            self.result_line_ids.filtered(
                lambda line: line.diagnostic_state == 'matched'
            )
        )
        self.only_remote_count = len(
            self.result_line_ids.filtered(
                lambda line: line.diagnostic_state == 'only_remote'
            )
        )
        self.only_local_count = len(
            self.result_line_ids.filtered(
                lambda line: line.diagnostic_state == 'only_local'
            )
        )
        self.conflict_count = len(
            self.result_line_ids.filtered(
                lambda line: line.diagnostic_state == 'conflict'
            )
        )

        conflicts = list(result['conflicts']) + heuristic_conflicts
        details = []
        if conflicts:
            details = conflicts[:5]
            if len(conflicts) > 5:
                details.append(
                    _('... y %s conflicto(s) más.') % (len(conflicts) - 5)
                )
        message = _(
            'Vinculación regla finalizada: %(applied)s línea(s) aplicada(s), %(skipped)s omitida(s).',
            applied=result['applied'],
            skipped=result['skipped'],
        )
        if details:
            message = '%s\n%s' % (message, '\n'.join(details))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Diagnóstico ARBA A122R'),
                'message': message,
                'type': 'warning'
                if conflicts or result['skipped']
                else 'success',
                'sticky': bool(conflicts or result['skipped']),
            },
        }


class ArbaA122rDiagnosticLine(models.TransientModel):
    _name = 'arba.a122r.diagnostic.line'
    _description = 'Resultado de diagnóstico ARBA A122R'
    _order = 'id'

    wizard_id = fields.Many2one(
        'arba.a122r.diagnostic.wizard', required=True, ondelete='cascade'
    )
    diagnostic_state = fields.Selection(
        [
            ('matched', 'Matcheada'),
            ('only_remote', 'Solo remota'),
            ('only_local', 'Solo local'),
            ('conflict', 'Conflicto'),
        ],
        required=True,
        string='Estado',
    )
    n_transaccion_agente = fields.Char(string='nTransaccionAgente')
    local_line_id = fields.Many2one(
        'account.payment.order.retention.line',
        string='Línea local',
        readonly=True,
    )
    payment_order_id = fields.Many2one(
        'account.payment.order',
        related='local_line_id.payment_order_id',
        string='Orden de pago',
        readonly=True,
    )
    local_sync_state = fields.Selection(
        [
            ('pending', 'Pendiente'),
            ('sent', 'Informada'),
            ('observed', 'Observada'),
            ('error', 'Error'),
            ('deleted', 'Dada de baja'),
        ],
        string='Estado sync local',
        readonly=True,
    )
    arba_id_dj = fields.Integer(string='ID DJ ARBA', readonly=True)
    arba_id_comprobante = fields.Integer(
        string='ID comprobante ARBA', readonly=True
    )
    arba_nro_emision = fields.Char(string='Nro emisión ARBA', readonly=True)
    remote_payload = fields.Text(string='Payload remoto', readonly=True)
    heuristic_candidate = fields.Boolean(
        string='Candidata por regla',
        readonly=True,
    )
    heuristic_match_key = fields.Char(
        string='Regla a usar',
        readonly=True,
    )
    note = fields.Char(string='Observación', readonly=True)
