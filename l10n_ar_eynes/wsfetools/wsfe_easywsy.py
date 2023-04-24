##############################################################################
#   Copyright (c) 2018 Eynes/E-MIPS (www.eynes.com.ar)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
##############################################################################

import logging
import time

from odoo import _
from odoo.exceptions import UserError

from ..wsfetools.ws_afip import AfipWS, AfipWSError, AfipWSEvent

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
                        'CbteTipo': int(voucher_type.afip_code),
                        'PtoVta': int(pos.code),
                        'CantReg': reg_qty,
                    },
                    'FeDetReq': {
                        'FECAEDetRequest': [],
                    },
                },
            },
        }
        details_array = data['FECAESolicitar']['FeCAEReq']['FeDetReq']['FECAEDetRequest']
        nn = False
        for inv_index, inv in enumerate(invoices):
            if first_number:
                nn = first_number + inv_index
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
            number = invoice.name.split("-")[1]
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
        products = all([ps == 'consu' or ps == 'product' for ps in product_service])

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
            'CbteFch': invoice_date.strftime('%Y%m%d'),
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
        is_not_anulation_fcred = invoice.is_FCE_invoice and invoice.optional_ids.filtered(
            lambda x: x.optional_id.code == '22' and x.value.strip().lower() == 'n'
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
            and invoice.type == 'out_invoice'
            and not invoice.is_debit_note
        ):
            detail['FchVtoPago'] = date_due
        # cbtes asoc

        # Associated Comps
        CbtesAsoc = []
        for associated_inv in invoice.associated_inv_ids:
            tipo_cbte = associated_inv.get_voucher_type().afip_code
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
                lambda o: {'Id': int(o.optional_id.code), 'Valor': o.value.strip()}
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
        not_found_tax = invoice.tax_line_ids.filtered(
            lambda x: x.amount and x.tax_id not in afip_taxes
        )
        if not_found_tax:
            err = _("Taxes `%s` are not configured in WSFE!") % (", ").join(
                not_found_tax.mapped('tax_id.name')
            )
            _logger.warning(_("Expected Error!\n") + err)

        # Procesamos las taxes

        vat_dict = {}
        for tax_line in invoice.tax_line_ids.filtered(lambda x: x.amount):
            afip_tax = conf.vat_tax_ids.filtered(lambda x: x.tax_id == tax_line.tax_id)
            if not afip_tax:
                continue
            # This should be a constraint in wsfe.tax.codes
            afip_tax.ensure_one()
            code = int(afip_tax.code)
            if code not in vat_dict:
                vat_dict[code] = {
                    'Importe': tax_line.amount,
                    'BaseImp': tax_line.base,
                }
            else:
                vat_dict[code]['Importe'] += tax_line.amount
                vat_dict[code]['BaseImp'] += tax_line.base

        vat_array = [{**{'Id': code}, **vals} for code, vals in vat_dict.items()]

        vat_tax_amount = sum(x['Importe'] for x in vat_dict.values())
        vat_base_amount = sum(x['BaseImp'] for x in vat_dict.values())

        tribute_tax_amount = sum(
            x.amount
            for x in invoice.tax_line_ids
            if x.tax_id not in afip_taxes and not x.tax_id.is_exempt
        )

        exempt_operation_amount = invoice.amount_exempt
        no_taxed_amount = invoice.amount_no_taxed

        base_amount = vat_base_amount
        tax_amount = tribute_tax_amount + vat_tax_amount

        total_amount = round(
            base_amount + no_taxed_amount + exempt_operation_amount + tax_amount,
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

            for det_req in self.last_request['args'][1].FeDetReq.FECAEDetRequest:
                if (
                    det_req['CbteDesde'] == det_response['CbteHasta']
                    and det_req['DocNro'] == det_req['DocNro']
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
            'PtoVta': int(pos),
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
                    doc_num = inv.partner_id.vat in [False, '', '0'] or doc_type == '99'
                else:
                    try:
                        doc_num = bool(int(inv.partner_id.vat))
                    except ValueError:
                        doc_num = False
                cbte = True
                if inv.internal_number:
                    cbte = comp['CbteHasta'] == int(inv.internal_number.split('-')[1])
                else:
                    # TODO: El nro de factura deberia unificarse
                    # para que se setee en una funcion
                    # o algo asi para que no haya posibilidad de que
                    # sea diferente nunca en su formato
                    invoice_vals['internal_number'] = '%04d-%08d' % (
                        res['PtoVta'],
                        comp['CbteHasta'],
                    )

                if not all([doc_tipo, doc_num, cbte]):
                    raise UserError(
                        _("WSFE Error!\n") + _("Validated invoice that not corresponds!")
                    )

                if comp['Resultado'] == 'A':
                    invoice_vals['cae'] = comp['CAE']
                    invoice_vals['cae_due_date'] = comp['CAEFchVto']
                    invoices_approved[inv.id] = invoice_vals

        return invoices_approved

    def log_request(self, environment):
        env = environment
        if not hasattr(self, 'last_request'):
            return False
        res = self.last_request['parse_result']
        wsfe_req_obj = env['wsfe.request']
        voucher_type_obj = env['wsfe.voucher_type']
        voucher_type = voucher_type_obj.search([('code', '=', res['CbteTipo'])])
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
                SELECT id FROM account_invoice WHERE id = %(id)s
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
                'voucher_date': comp['CbteFch'],
                'amount_total': comp['ImpTotal'],
                'cae': comp['CAE'],
                'cae_duedate': comp['CAEFchVto'],
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
        if not hasattr(self, 'auth') or not self.auth or self.auth.attrs['Token'] == 'T':
            if not conf:
                conf = invoices.get_ws_conf()
            token, sign = conf.wsaa_ticket_id.get_token_sign()
            auth = {'Token': token, 'Sign': sign, 'Cuit': conf.cuit}
            self.login('Auth', auth)
            auth_instance = getattr(self.data.FECAESolicitar, self.auth._element_name)
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
