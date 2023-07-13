##############################################################################
#   Copyright (c) 2018 Eynes/E-MIPS (www.eynes.com.ar)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
##############################################################################

import logging
import time
from datetime import datetime

from odoo import _, fields
from odoo.exceptions import UserError

from ..wsfetools.ws_afip import AfipWS, AfipWSError, AfipWSEvent, WsApi

_logger = logging.getLogger(__name__)


DATE_FORMAT = '%Y-%m-%d'
AFIP_DATE_FORMAT = '%Y%m%d'


class WSFE(AfipWS):
    def parse_invoices(self, invoices, first_number=False):
        reg_qty = len(invoices)
        voucher_type = invoices[0].get_voucher_type()
        pos = invoices[0].get_pos()
        data = {
            'FECAESolicitar': {
                'FeCAEReq': {
                    'FeCabReq': {
                        'CbteTipo': voucher_type,
                        'PtoVta': pos,
                        'CantReg': reg_qty,
                    },
                    'FeDetReq': {
                        'FECAEDetRequest': [],
                    },
                },
            },
        }
        details_array = data['FECAESolicitar']['FeCAEReq']['FeDetReq'][
            'FECAEDetRequest'
        ]
        nn = False
        for inv_index, inv in enumerate(invoices):
            if first_number:
                nn = int(first_number) + inv_index
            inv_data = self.parse_invoice(inv, number=nn, invoices=invoices)
            inv_data['first_of_lot'] = False
            if (first_number and nn == first_number) or len(invoices) == 1:
                inv_data['first_of_lot'] = True
            details_array.append(inv_data)
        import pprint

        pprint.pprint(data)
        return data

    def parse_invoice(self, invoice, number=False, invoices=False):
        invoice.ensure_one()
        if not number:
            number = invoice.get_next_wsfe_number()
        invoice_date = invoice.invoice_date
        formatted_invoice_date = invoice_date.strftime('%Y%m%d')
        date_due = (
            invoice.invoice_date_due
            and invoice.invoice_date_due.strftime('%Y%m%d')
            or formatted_invoice_date
        )

        # Chequeamos si el concepto es producto,
        # servicios o productos y servicios
        product_service = [
            line.product_id and line.product_id.type or 'consu'
            for line in invoice.invoice_line_ids
        ]

        service = all([ps == 'service' for ps in product_service])
        products = all(
            [ps == 'consu' or ps == 'product' for ps in product_service]
        )

        # Calculamos el concepto de la factura, dependiendo de las
        # lineas de productos que se estan vendiendo
        concept = None
        if products:
            concept = 1  # Productos
        elif service:
            concept = 2  # Servicios
        else:
            concept = 3  # Productos y Servicios

        doc_type = (
            invoice.partner_id.document_type_id
            and invoice.partner_id.document_type_id.afip_code
            or '99'
        )
        doc_num = (invoice.partner_id.vat or '0') if doc_type != '99' else '0'

        company_id = invoice.env.user.company_id
        company_currency_id = company_id.currency_id

        ars_cur = invoice.env.ref('base.ARS')
        if invoice.currency_id == ars_cur:
            currency_code = 'PES'
        else:
            currency_code = invoice.get_currency_code()
        # Cotizacion
        invoice_rate = 1.0
        if invoice.currency_id.id != company_currency_id.id:
            invoice_rate = invoice.currency_rate

        iva_values = self.get_vat_array(invoice)

        detail = {
            'invoices': invoices,
            'invoice': invoice,
            'CbteDesde': number,
            'CbteHasta': number,
            'CbteFch': formatted_invoice_date,
            'Concepto': concept,
            'DocNro': doc_num,
            'DocTipo': doc_type,
            'FchServDesde': False,
            'FchServHasta': False,
            'FchVtoPago': False,
            'MonId': currency_code,
            'MonCotiz': invoice_rate,
        }

        detail.update(iva_values)
        detail = invoice.hook_add_taxes(invoice, detail)
        is_not_anulation_fcred = (
            invoice.is_FCE_invoice
            and invoice.optional_ids.filtered(
                lambda x: x.optional_id.code == '22'
                and x.value.strip().lower() == 'n'
            )
        )
        if concept in [2, 3]:
            detail.update(
                {
                    'FchServDesde': formatted_invoice_date,
                    'FchServHasta': formatted_invoice_date,
                }
            )
            if not is_not_anulation_fcred:
                detail['FchVtoPago'] = date_due
            # elif invoice.is_FCE_invoice and invoice.type == 'out_invoice' /
            #   and not invoice.is_debit_note:
            #     detail['FchVtoPago'] = date_due
        if (
            invoice.is_FCE_invoice
            and invoice.move_type == 'out_invoice'
            and not invoice.is_debit_note
        ):
            detail['FchVtoPago'] = date_due
        # cbtes asoc

        # Associated Comps
        CbtesAsoc = []
        for associated_inv in invoice.associated_inv_ids:
            tipo_cbte = associated_inv.get_voucher_type()
            pos, number = associated_inv.name.split('-')
            cbte_fch = associated_inv.invoice_date.strftime('%Y%m%d')
            CbteAsoc = {
                'Tipo': tipo_cbte,
                'PtoVta': int(pos),
                'Nro': int(number),
                'Cuit': invoice.company_id.partner_id.vat,
                'CbteFch': cbte_fch,
                'invoice': associated_inv,
                'Concepto': False,
            }
            CbtesAsoc.append(CbteAsoc)
        if CbtesAsoc:
            detail['CbtesAsoc'] = {'CbteAsoc': CbtesAsoc}

        # optionals
        detail['Opcionales'] = {
            'Opcional': invoice.optional_ids
            and invoice.optional_ids.mapped(
                lambda o: {
                    'Id': int(o.optional_id.code),
                    'Valor': o.value.strip(),
                }
            )
            or []
        }

        if not hasattr(self.data, 'sent_invoices'):
            self.data.sent_invoices = {}
        self.data.sent_invoices[invoice] = detail
        _logger.info('Data to send afip is below:')
        _logger.info(detail)
        return detail

    def get_vat_array(self, invoice, retry=False):
        invoice.ensure_one()
        conf = invoice.get_ws_conf()

        afip_taxes = conf.vat_tax_ids.mapped('tax_id')
        invoice_tax_lines = invoice.line_ids.filtered(
            lambda x: x.price_unit and x.tax_line_id
        )
        not_found_tax = invoice_tax_lines.filtered(
            lambda x: x.tax_line_id not in afip_taxes
        )
        if not_found_tax:
            err = _("Taxes `%s` are not configured in WSFE!") % (", ").join(
                not_found_tax.mapped('tax_line_id.name')
            )
            _logger.warning(_("Expected Error!\n") + err)

        # Procesamos las taxes

        vat_dict = {}
        for tax_line in invoice_tax_lines:
            afip_tax = conf.vat_tax_ids.filtered(
                lambda x: x.tax_id == tax_line.tax_line_id
            )
            if not afip_tax:
                continue
            # This should be a constraint in wsfe.tax.codes
            afip_tax.ensure_one()
            code = int(afip_tax.code)
            if code not in vat_dict:
                vat_dict[code] = {
                    'Importe': tax_line.price_unit,
                    'BaseImp': tax_line.tax_base_amount / invoice.currency_rate
                    if not invoice.is_company_cur
                    else tax_line.tax_base_amount,
                }
            else:
                vat_dict[code]['Importe'] += tax_line.price_unit
                if invoice.is_company_cur:
                    vat_dict[code]['BaseImp'] += tax_line.tax_base_amount
                else:
                    vat_dict[code]['BaseImp'] += (
                        tax_line.tax_base_amount / invoice.currency_rate
                    )

        vat_array = [
            {**{'Id': code}, **vals} for code, vals in vat_dict.items()
        ]

        vat_tax_amount = sum(x['Importe'] for x in vat_dict.values())
        vat_base_amount = sum(x['BaseImp'] for x in vat_dict.values())

        # Chequear este calculo: qué debería sumar?
        tribute_tax_amount = sum(
            x.price_unit
            for x in invoice_tax_lines
            if x.tax_line_id not in afip_taxes and not x.tax_line_id.is_exempt
        )

        exempt_operation_amount = invoice.amount_exempt
        no_taxed_amount = invoice.amount_no_taxed

        base_amount = vat_base_amount
        tax_amount = tribute_tax_amount + vat_tax_amount

        total_amount = round(
            base_amount
            + no_taxed_amount
            + exempt_operation_amount
            + tax_amount,
            self._decimal_precision,
        )

        invoice.check_invoice_total(total_amount)

        vals = {
            'number': invoice.name,
            'id': invoice.id,
            'ImpIVA': vat_tax_amount,
            'ImpNeto': vat_base_amount,
            'ImpOpEx': exempt_operation_amount,
            'ImpTotal': total_amount,
            'ImpTotConc': no_taxed_amount,
            'ImpTrib': tribute_tax_amount,
            'Iva': {
                'AlicIva': vat_array,
            },
        }
        self._afip_round(vals)
        log = (
            'Procesando Factura Electronica: %(number)s (id: %(id)s)\n'
            + 'Importe Total: %(ImpTotal)s\n'
            + 'Importe Neto Gravado: %(ImpNeto)s\n'
            + 'Importe IVA: %(ImpIVA)s\n'
            + 'Importe Tributos: %(ImpTrib)s\n'
            + 'Importe Operaciones Exentas: %(ImpOpEx)s\n'
            + 'Importe Neto no Gravado: %(ImpTotConc)s\n'
            + 'Array de IVA: %(Iva)s\n'
        ) % vals
        _logger.info(log)
        vals.pop('number')
        vals.pop('id')
        return vals

    def get_response_matching_invoice(self, resp):
        _inv = False
        for _inv, vals in self.data.sent_invoices.items():
            if (
                resp['CbteDesde'] == vals['CbteDesde']
                and resp['CbteFch'] == vals['CbteFch']
            ):
                break
        return _inv

    def _parse_errors(self, response):
        errors = []
        if 'Errors' in response:
            for e in response.Errors.Err:
                error = '%s (Err. %s)' % (e.Msg, e.Code)
                errors.append(error)
        return errors

    def _parse_observations(self, det_response):
        observations = []
        if 'Observaciones' in det_response:
            for o in det_response.Observaciones.Obs:
                observ = '%s (Err. %s)' % (o.Msg, o.Code)
                observations.append(observ)
        return observations

    def _parse_invoices(self, response):
        invoices = []

        for det_response in response.FeDetResp.FECAEDetResponse:
            observations = self._parse_observations(det_response)

            for det_req in self.last_request['args'][
                1
            ].FeDetReq.FECAEDetRequest:
                if (
                    int(det_req['CbteDesde']) == det_response['CbteHasta']
                    and int(det_req['DocNro']) == det_response['DocNro']
                ):
                    MonId = det_req['MonId']
                    MonCotiz = det_req['MonCotiz']
                    ImpTotal = det_req['ImpTotal']
                    break

            comp = {
                'Concepto': det_response.Concepto,
                'DocTipo': det_response.DocTipo,
                'DocNro': det_response.DocNro,
                'CbteDesde': det_response.CbteDesde,
                'CbteHasta': det_response.CbteHasta,
                'CbteFch': det_response.CbteFch,
                'Resultado': det_response.Resultado,
                'CAE': det_response.CAE,
                'CAEFchVto': det_response.CAEFchVto,
                'Observaciones': observations,
                'MonId': MonId,
                'MonCotiz': MonCotiz,
                'ImpTotal': ImpTotal,
            }
            invoice = self.get_response_matching_invoice(comp)
            comp['invoice'] = invoice
            invoices.append(comp)

        return invoices, invoice

    def parse_invoices_response(self, response):
        errors = self._parse_errors(response)
        invoices, invoice = self._parse_invoices(response)

        pos = invoice.get_pos()
        res = {
            'Comprobantes': invoices,
            'Errores': errors,
            'PtoVta': pos,
            'Resultado': response.FeCabResp.Resultado,
            'Reproceso': response.FeCabResp.Reproceso,
            'CbteTipo': response.FeCabResp.CbteTipo,
            'CantReg': response.FeCabResp.CantReg,
        }
        self.last_request['parse_result'] = res
        invoices_approved = {}

        # Verificamos el resultado de la Operacion
        # Si no fue aprobado
        if res['Resultado'] == 'R':
            msg = ''
            if res['Errores']:
                msg = 'Errores: ' + '\n'.join(res['Errores']) + '\n'
                msg = msg.encode('latin1').decode('utf8')
            if res['Comprobantes'][0]['Observaciones']:
                msg += '\nObservaciones: ' + '\n'.join(
                    res['Comprobantes'][0]['Observaciones']
                )
                # msg = msg.encode('latin1').decode('utf8')

            if invoice._context.get('raise-exception', True):
                raise UserError(
                    _(
                        'AFIP Web Service Error\n'
                        + 'La factura no fue aprobada. \n'
                        + '%s'
                    )
                    % msg
                )

        elif res['Resultado'] == 'A' or res['Resultado'] == 'P':
            for comp in res['Comprobantes']:
                invoice_vals = {}
                inv = comp['invoice']
                if comp['Observaciones']:
                    msg = 'Observaciones: ' + '\n'.join(comp['Observaciones'])

                # Chequeamos que se corresponda con la
                # factura que enviamos a validar
                doc_type = (
                    inv.partner_id.document_type_id
                    and inv.partner_id.document_type_id.afip_code
                    or '99'
                )
                doc_tipo = comp['DocTipo'] == int(doc_type)
                if comp['DocNro'] == 0:
                    doc_num = (
                        inv.partner_id.vat in [False, '', '0']
                        or doc_type == '99'
                    )
                else:
                    try:
                        doc_num = bool(int(inv.partner_id.vat))
                    except ValueError:
                        doc_num = False

                invoice_vals['name'] = '%04d-%08d' % (
                    res['PtoVta'],
                    comp['CbteHasta'],
                )

                if not all([doc_tipo, doc_num]):
                    raise UserError(
                        _("WSFE Error!\n")
                        + _("Validated invoice that not corresponds!")
                    )

                if comp['Resultado'] == 'A':
                    invoice_vals['cae'] = comp['CAE']
                    invoice_vals['cae_due_date'] = "{y}-{m}-{d}".format(
                        y=comp['CAEFchVto'][:4],
                        m=comp['CAEFchVto'][4:6],
                        d=comp['CAEFchVto'][6:],
                    )
                    invoices_approved[inv.id] = invoice_vals

        return invoices_approved

    def log_request(self, environment):
        env = environment
        if not hasattr(self, 'last_request'):
            return False
        res = self.last_request['parse_result']
        wsfe_req_obj = env['wsfe.request']
        voucher_type_obj = env['res.voucher.type']
        req_vtype = str(res['CbteTipo']).zfill(3)
        voucher_type = voucher_type_obj.search([('afip_code', '=', req_vtype)])
        voucher_type_name = ', '.join(x.name for x in voucher_type)
        req_details = []
        pos = res['PtoVta']
        for _index, comp in enumerate(res['Comprobantes']):

            # Esto es para fixear un bug que al hacer un refund,
            # si fallaba algo con la AFIP
            # se hace el rollback por lo tanto el refund que se estaba
            # creando ya no existe en
            # base de datos y estariamos violando una foreign
            # key contraint. Por eso,
            # chequeamos que existe info de la invoice_id,
            # sino lo seteamos en False
            read_inv = comp['invoice']

            if not read_inv:
                invoice_id = False
            else:
                invoice_id = read_inv.id
                q = """
                SELECT id FROM account_move WHERE id = %(id)s
                """
                env.cr.execute(q, {'id': invoice_id})
                # Invoice Failed to create and does not exist in the DB
                if not env.cr.rowcount:
                    invoice_id = False

            det = {
                'name': invoice_id,
                'concept': str(comp['Concepto']),
                'doctype': comp[
                    'DocTipo'
                ],  # TODO: Poner aca el nombre del tipo de documento  # noqa
                'docnum': str(comp['DocNro']),
                'voucher_number': comp['CbteHasta'],
                'voucher_date': "{y}-{m}-{d}".format(
                    y=comp['CbteFch'][:4],
                    m=comp['CbteFch'][4:6],
                    d=comp['CbteFch'][6:],
                ),
                'amount_total': comp['ImpTotal'],
                'cae': comp['CAE'],
                'cae_duedate': "{y}-{m}-{d}".format(
                    y=comp['CAEFchVto'][:4],
                    m=comp['CAEFchVto'][4:6],
                    d=comp['CAEFchVto'][6:],
                ),
                'result': comp['Resultado'],
                'currency': comp['MonId'],
                'currency_rate': comp['MonCotiz'],
                # 'observations': '\n'.join(comp['Observaciones']).encode(
                # 'latin1').decode('utf8'),
                'observations': '\n'.join(comp['Observaciones']),
            }

            req_details.append((0, 0, det))

        # Chequeamos el reproceso
        reprocess = False
        if res['Reproceso'] == 'S':
            reprocess = True

        errors = '\n'.join(res['Errores']).encode('latin1').decode('utf8')
        vals = {
            'voucher_type': voucher_type_name,
            'nregs': len(res['Comprobantes']),
            'pos_ar': '%04d' % int(pos),
            'date_request': time.strftime('%Y-%m-%d %H:%M:%S'),
            'result': res['Resultado'],
            'reprocess': reprocess,
            'errors': errors,
            'detail_ids': req_details,
        }

        return wsfe_req_obj.create(vals)

    def send_invoice(self, invoice, first_number=False):
        """
        A mask for send_invoices
        """
        return self.send_invoices(invoice, first_number=first_number)

    def send_invoices(self, invoices, first_number=False, conf=False):
        invoices.complete_date_invoice()
        data = self.parse_invoices(invoices, first_number=first_number)
        self.auth_decoy()
        self.add(data)
        if (
            not hasattr(self, 'auth')
            or not self.auth
            or self.auth.attrs['Token'] == 'T'
        ):
            if not conf:
                conf = invoices.get_ws_conf()
            token, sign = conf.wsaa_ticket_id.get_token_sign()
            auth = {'Token': token, 'Sign': sign, 'Cuit': conf.cuit}
            self.login('Auth', auth)
            auth_instance = getattr(
                self.data.FECAESolicitar, self.auth._element_name
            )
            for k, v in self.auth.attrs.items():
                setattr(auth_instance, k, v)
        _logger.info(self.data.FECAESolicitar)
        response = self.request('FECAESolicitar')
        _logger.info(response)
        approved = self.parse_invoices_response(response)
        return approved

    ###############################################################################

    def _get_errors(self, result):
        errors = []
        if 'Errors' in result:
            for error in result.Errors.Err:
                error = AfipWSError(error.Code, error.Msg)
                errors.append(error)
        return errors

    def _get_events(self, result):
        events = []
        if 'Events' in result:
            for event in result.Events.Evt:
                event = AfipWSEvent(event.Code, event.Msg)
                events.append(event)
        return events

    ###############################################################################
    # AFIP Data Validation Methods According to:
    # http://afip.gob.ar/fe/documentos/manual_desarrollador_COMPG_v2_11.pdf

    NATURALS = [
        'CantReg',
        'CbteTipo',
        'PtoVta',
        'DocTipo',
        'CbteHasta',
        'CbteNro',
        'Id',
    ]

    POSITIVE_REALS = [
        'ImpTotal',
        'ImpTotConc',
        'ImpNeto',
        'ImpOpEx',
        'ImpIVA',
        'ImpTrib',
        'BaseImp',
        'Importe',
    ]

    STRINGS = ['MonId']

    @staticmethod
    @WsApi.check(['DocNro'], reraise=True, sequence=20)
    def validate_docnro(val, invoice, DocTipo):
        tin_type = int(DocTipo)
        if tin_type != 99:
            tin_number = int(val)
        else:
            tin_number = val
        if invoice.denomination == 'b':
            if tin_type != 99 and not tin_number:
                return False
            if invoice.amount_total >= 5000:
                if not tin_number:
                    return False
            else:
                if tin_type == 99 and tin_number != '0':
                    return False
        if invoice.denomination == 'a':
            if not int(val):
                return False
        return True

    @staticmethod
    @WsApi.check(['CbteDesde'], reraise=True, sequence=20)
    def validate_invoice_number(val, invoice, invoices, first_of_lot=True):
        return True

    @staticmethod
    @WsApi.check(NATURALS)
    def validate_natural_number(val):
        val = int(val)
        if val > 0:
            return True
        return False

    @staticmethod
    @WsApi.check(POSITIVE_REALS)
    def validate_positive_reals(val):
        if not val or (isinstance(val, float) and val > 0):
            return True
        return False

    @staticmethod
    @WsApi.check(STRINGS)
    def validate_strings(val):
        if isinstance(val, str):
            return True
        return False

    @staticmethod
    @WsApi.check(['Concepto'])
    def validate_concept(val):
        if val in [1, 2, 3]:
            return True
        return False

    @staticmethod
    @WsApi.check(['FchServDesde'])
    def validate_service_from_date(val, Concepto):
        if Concepto not in [2, 3]:
            return True
        datetime.strptime(val, AFIP_DATE_FORMAT)
        return True

    @staticmethod
    @WsApi.check(['FchServHasta'])
    def validate_service_to_date(val, FchServDesde, Concepto):
        if Concepto not in [2, 3]:
            return True
        datetime.strptime(val, AFIP_DATE_FORMAT)
        if val >= FchServDesde:
            return True
        return False

    @staticmethod
    @WsApi.check(['FchVtoPago'])
    def validate_service_payment_date(val, invoice, Concepto):
        if Concepto not in [2, 3]:
            return True
        # No checks if invoice is of mipyme.fcred
        if invoice.is_FCE_invoice:
            return True
        datetime.strptime(val, AFIP_DATE_FORMAT)
        inv_date = invoice.invoice_date or fields.Date.context_today(invoice)
        inv_date = inv_date.strftime(AFIP_DATE_FORMAT)
        if val >= inv_date.replace('-', ''):
            return True
        return False

    @staticmethod
    @WsApi.check(['CbteFch'], reraise=True)
    def validate_invoice_date(val, invoice, Concepto):
        if not val:
            return True
        val_date = datetime.strptime(val, AFIP_DATE_FORMAT)
        last_invoiced_date = invoice.get_last_date_invoice()
        conf = invoice.get_ws_conf()

        if last_invoiced_date and val_date.date() < last_invoiced_date:
            raise UserError(
                _('WSFE Error!\n')
                + _(
                    'There is another Invoice with a most recent date [%s] '
                    + 'for the same Point of Sale and Denomination.'
                )
                % last_invoiced_date
            )
        today = fields.Date.context_today(invoice)
        offset = today - val_date.date()
        if Concepto in [2, 3]:
            if abs(offset.days) > conf.services_date_difference:
                raise UserError(
                    _('WSFE Error!\n')
                    + _(
                        'Invoice Date difference with today should be less '
                        + 'than [%s] days for products and services sales.'
                    )
                    % conf.services_date_difference
                )
        else:
            if abs(offset.days) > conf.products_date_difference:
                raise UserError(
                    _('WSFE Error!\n')
                    + _(
                        'Invoice Date difference with today should be less '
                        + 'than [%s] days for product sales.'
                    )
                    % conf.products_date_difference
                )
        return True

    @staticmethod
    @WsApi.check(['MonCotiz'])
    def validate_currency_rate(val, MonId):
        if MonId == 'PES':
            if val == 1:
                return True
        else:
            if isinstance(val, float):
                return True
        return False

    @staticmethod
    @WsApi.check(['Tipo', 'Nro'])
    def validate_cmps_tipo(val, Tipo):
        return True

    @staticmethod
    @WsApi.check(['Valor'])
    def validate_cmps_valor(val, Valor):
        return True

    @staticmethod
    @WsApi.check(['Alic', 'Desc'])
    def validate_tributos(val, Alic):
        return True
