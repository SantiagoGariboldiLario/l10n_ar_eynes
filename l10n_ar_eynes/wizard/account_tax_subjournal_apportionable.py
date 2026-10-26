import json
import logging
import time
from calendar import monthrange
from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


def _clean_tax_name(name):
    """Clean tax name to remove 'Percepciones' and 'Efectuadas'."""
    if not name:
        return ''
    changes_map = {
        'Percepciones ': 'Perc.',
        'Retenciones ': 'Ret.',
        ' Efectuadas': '',
        ' efectuadas': '',
        ' Sufridos': '',
        ' sufridos': '',
        ' Sufridas': '',
        ' sufridas': '',
        ' Sufrido': '',
        ' sufrido': '',
        ' Sufrida': '',
        ' sufrida': '',
        ' Sufr.': '',
        ' sufr.': '',
        ' Sufr': '',
        ' sufr': '',
        'IVA Ventas ': '',
        'IVA Compras ': '',
        'Ganancias ': 'Gcias.',
        'Impuesto ': 'Imp.',
        'Interno ': 'Int.',
        '10.50': '10.5',
        '21.00': '21.0',
        '27.00': '27.0',
    }
    for old, new in changes_map.items():
        name = name.replace(old, new)
    return name.strip()


class AccountTaxSubjournalApportionableWizard(models.TransientModel):
    _name = 'account.tax.subjournal.apportionable.wizard'
    _description = (
        "Account tax subjournal report wizard for apportionable VAT taxes"
    )

    based_on = fields.Selection(
        [('sale', 'Sales'), ('purchase', 'Purchases')],
        string='Based On',
        required=True,
        default='sale',
    )
    base_position = fields.Selection(
        [('first', 'First'), ('second', 'Second')],
        string='Base Column Position',
        required=True,
        default='first',
    )
    company_id = fields.Many2one('res.company', 'Company', required=True)
    company_id_domain = fields.Char(
        default=lambda self: self._default_company_ids()
    )
    date_from = fields.Date(
        string='Start of period',
        default=time.strftime('%Y-%m-01'),
    )
    date_to = fields.Date(string='End of period', default=fields.Date.today)
    grouped = fields.Boolean(
        string="Grouped",
        help="Type B Invoices below the grouped max amount will be "
        "grouped in a single line per day and tax.",
    )
    grouped_max_amount = fields.Float(
        string="Grouped Max Amount",
        help="If grouped is checked, this will determine the "
        + "grouping threshold",
    )
    perception_retention_grouped = fields.Boolean(
        string="Perception / Retention Grouped",
        help="Group by retention / perception "
        + "grouped in a single column retention / perception.",
    )
    sort_by = fields.Selection(
        [('sequence', 'Sequence'), ('name', 'Name')],
        string='Sort Taxes by',
        required=True,
        default='sequence',
    )

    @api.model
    def _default_company_ids(self):
        return json.dumps(
            [('id', 'in', self.env.context.get('allowed_company_ids', []))]
        )

    @api.onchange('date_from')
    def _onchange_date_from(self):
        end_of_month = monthrange(self.date_from.year, self.date_from.month)[1]
        self.date_to = self.date_from.replace(day=end_of_month)

    def _do_validations(self):
        if self.date_from != self.date_from.replace(day=1):
            raise ValidationError(
                _("You should only select the first day of month")
            )

    # DATA QUE SE NECESITA PARA ARMAR EL REPORTE SUBDIARIO DE IVA
    def _get_title(self):
        sub_type = 'Ventas'
        if self.based_on == 'purchase':
            sub_type = 'Compras'

        title = 'Libro IVA %s con IVA prorrateable - Periodo %s a %s' % (
            sub_type,
            self.date_from,
            self.date_to,
        )
        return title

    def _get_apport_block_title(self, order):
        if self.based_on == 'purchase':
            end = 'CRÉDITO'
            if order == 'second':
                end = 'DÉBITO'
        else:
            end = 'DÉBITO'
            if order == 'second':
                end = 'CRÉDITO'
        return 'TOTAL DE OPERACIONES QUE GENERAN %s FISCAL' % end

    def _get_move_types(self):
        return (
            ('out_invoice', 'out_refund')
            if self.based_on == 'sale'
            else ('in_invoice', 'in_refund')
        )

    def _get_invoice_type(self, voucher_type, denom):
        voucher_mapping = {
            '001': 'F ',
            '002': 'ND ',
            '003': 'NC ',
            '006': 'F ',
            '007': 'ND ',
            '008': 'NC ',
            '011': 'F ',
            '012': 'ND ',
            '013': 'NC ',
            '017': 'LSP ',
            '018': 'LSP ',
            '019': 'F ',
            '051': 'F ',
            '052': 'ND ',
            '053': 'NC ',
            '066': 'DES ',
            '099': 'F ',
            '090': 'NC ',
            '201': 'FCE ',
            '202': 'NDE ',
            '203': 'NCE ',
            '206': 'FCE ',
            '207': 'NDE ',
            '208': 'NCE ',
        }
        return '%s %s' % (voucher_mapping[voucher_type], denom.upper())

    def _get_columns(self):
        taxes = self._get_taxes_vals()
        all_taxes = []
        vat_taxes = []

        already_vat = False
        already_gross = False
        already_income = False

        for tax in taxes:
            tax_id = tax.get('tax_id', False)
            if tax_id:
                name = tax.get('name', '')
                name = name.get('es_AR', name.get('en_US', '')) if name else ''
                if tax.get('group_type', '') == 'internals':
                    name = 'Imp.Interno'
                tax_vals = {
                    'id': tax_id,
                    'is_exempt': tax.get('is_exempt', False),
                    'name': name,
                    'type': 'tax',
                }
                if tax.get('group_type', '') == 'vat':
                    if not tax.get('is_exempt'):
                        # The summary is keyed by aliquot ('21.0%'), so use the
                        # tax rate instead of its name ('IVA Compras 21%')
                        tax_vals['name'] = '%.2f%%' % (tax.get('amount') or 0.0)
                    vat_taxes.append(tax_vals)
                else:
                    retention_type = tax.get('retention_type', '')
                    if (
                        self.perception_retention_grouped
                        and retention_type
                        in [
                            'gross_income',
                            'vat',
                            'profit',
                        ]
                    ):
                        if (
                            retention_type == 'gross_income'
                            and not already_gross
                        ):
                            already_gross = True
                            gross_vals = {
                                'id': False,
                                'ids': [
                                    t.get('tax_id', False)
                                    for t in taxes
                                    if t.get('retention_type', '')
                                    == 'gross_income'
                                ],
                                'names': [
                                    t.get('name', '')
                                    for t in taxes
                                    if t.get('retention_type', '')
                                    == 'gross_income'
                                ],
                                'is_exempt': tax.get('is_exempt', False),
                                'name': 'Retenciones / Percepciones IIBB',
                                'type': 'gross_income',
                            }
                            all_taxes.append(gross_vals)
                        elif retention_type == 'vat' and not already_vat:
                            already_vat = True
                            vat_vals = {
                                'id': False,
                                'ids': [
                                    t.get('tax_id', False)
                                    for t in taxes
                                    if t.get('retention_type', '') == 'vat'
                                ],
                                'names': [
                                    t.get('name', '')
                                    for t in taxes
                                    if t.get('retention_type', '') == 'vat'
                                ],
                                'is_exempt': tax.get('is_exempt', False),
                                'name': 'Retenciones / Percepciones IVA',
                                'type': 'vat',
                            }
                            all_taxes.append(vat_vals)
                        elif retention_type == 'profit' and not already_income:
                            already_income = True
                            income_vals = {
                                'id': False,
                                'ids': [
                                    t.get('tax_id', False)
                                    for t in taxes
                                    if t.get('retention_type', '') == 'profit'
                                ],
                                'names': [
                                    t.get('name', '')
                                    for t in taxes
                                    if t.get('retention_type', '') == 'profit'
                                ],
                                'is_exempt': tax.get('is_exempt', False),
                                'name': 'Retenciones / Percepciones Ganancias',
                                'type': 'profit',
                            }
                            all_taxes.append(income_vals)
                        continue

                    all_taxes.append(tax_vals)
        return all_taxes, vat_taxes

    def _group_lines_data(self, cols, vat_cols):  # noqa: C901
        query_vals = self._get_line_vals()
        if not len(query_vals):
            raise UserError(_('There were no moves for this period'))

        c_taxes = [0] * len(cols)
        vat_ids = {tax['id'] for tax in vat_cols}
        final_consumer_id = self.env.ref('l10n_ar_eynes.fiscal_position_cf').id
        ri_id = self.env.ref('l10n_ar_eynes.fiscal_position_ri').id

        lines = {}
        last_line_id = -1
        retention_perception_summary = {}
        for line in query_vals:
            is_final_consumer = line['fpid'] == final_consumer_id
            based_sign = 1

            if self.based_on == 'purchase':
                based_sign = -1

            invoice_type = self._get_invoice_type(
                line['voucher_type'], line['denomination']
            )
            key = line['invoice_id']
            line_id = line['line_id']
            amount = (line['credit'] - line['debit']) * based_sign

            if (
                self.grouped
                and is_final_consumer
                and line['invoice_total'] < self.grouped_max_amount
            ):
                key = 'cf' + line['date'].strftime('%d/%m/%Y') + invoice_type
                lines.setdefault(
                    key,
                    {
                        'invoice_number': '',
                        'date': line['date'],
                        'invoice_type': invoice_type,
                        'partner_name': 'Agrupado CF monto menor a %s'
                        % round(self.grouped_max_amount, 2),
                        'partner_vat': '',
                        'partner_ri': False,
                        'total': 0.0,
                        'taxes': [0] * len(cols),
                        'vat_taxes': {},
                        'no_taxed': 0.0,
                    },
                )
            else:
                lines.setdefault(
                    key,
                    {
                        'invoice_number': line['invoice_number'],
                        'date': line['date'],
                        'invoice_type': invoice_type,
                        'partner_name': line['partner'],
                        'partner_vat': line['vat'],
                        'partner_ri': line['fpid'] == ri_id,
                        'total': 0.0,
                        'taxes': [0] * len(cols),
                        'vat_taxes': {},
                        'no_taxed': 0.0,
                    },
                )

            if last_line_id != line_id:
                last_line_id = line_id
                lines[key]['total'] += amount

            for i, tax in enumerate(cols):
                if self.perception_retention_grouped:
                    tax_ids = tax.get('ids', False)
                    if tax_ids:
                        if line['tax_line_id'] in tax_ids:
                            tax_index = tax_ids.index(line['tax_line_id'])
                            # LINEA DE IMPUESTO
                            lines[key]['taxes'][i] += amount
                            retention_perception_summary.setdefault(
                                line['tax_line_id'],
                                [tax.get('names', [])[tax_index], 0.0],
                            )
                            retention_perception_summary[line['tax_line_id']][
                                1
                            ] += amount
                        if lines[key]['taxes'][i] != 0:
                            c_taxes[i] += 1

                if (
                    # LINEA DE IMPUESTO
                    line['tax_line_id'] == tax['id']
                    and tax['type'] == 'tax'
                ) or (
                    # LINEA DE PRODUCTO (BASE DE IMPUESTO)
                    line['tax_ids'] == tax['id']
                    and tax['type'] == 'base'
                ):
                    lines[key]['taxes'][i] += amount
                    if lines[key]['taxes'][i] != 0:
                        c_taxes[i] += 1

            for _i, tax in enumerate(vat_cols):
                tax_id = tax.get('id', -1)
                if (
                    # LINEA DE PRODUCTO (BASE DE IMPUESTO)
                    line['tax_ids']
                    == tax_id
                ):
                    lines[key]['vat_taxes'].setdefault(
                        tax_id,
                        {
                            'name': _clean_tax_name(tax.get('name', '')),
                        },
                    )
                    lines[key]['vat_taxes'][tax_id].setdefault(
                        line['fiscal_credit'], 0.0
                    )
                    lines[key]['vat_taxes'][tax_id][
                        line['fiscal_credit']
                    ] += amount
            self._add_vat_tax_line(lines[key], line, vat_ids, amount)

            if not (line['tax_line_id'] or line['tax_ids']):
                # SI NO ES LINEA DE IMPUESTO O ES LINEA SIN IMPUESTOS CORRESPONDE A NO GRAVADO
                lines[key]['no_taxed'] += amount

        return lines, c_taxes, retention_perception_summary

    def _add_vat_tax_line(self, invoice_vals, line, vat_ids, amount):
        """Keep the VAT of the tax lines, to report the invoice amount
        instead of recalculating it from the base."""
        tax_id = line['tax_line_id']
        if tax_id in vat_ids:
            vat_amounts = invoice_vals.setdefault('vat_amounts', {})
            vat_amounts[tax_id] = vat_amounts.get(tax_id, 0.0) + amount

    def _split_vat_amount(self, invoice_vals, tax_id, vat_values):
        """VAT amount by fiscal credit. Tax lines have no fiscal credit, so
        the invoice VAT is split by base (the last one takes the rest).
        Without tax line it is calculated from the base."""
        bases = {
            fiscal_credit: base
            for fiscal_credit, base in vat_values.items()
            if fiscal_credit not in ('name', 'is_exempt')
        }
        total = invoice_vals.get('vat_amounts', {}).get(tax_id)
        if total is None:
            try:
                rate = float(vat_values['name'].replace('%', '')) / 100
            except ValueError:
                rate = 0.0
            return {fc: round(base * rate, 2) for fc, base in bases.items()}
        total_base = sum(bases.values())
        fiscal_credits = list(bases)
        res = {}
        pending = total
        for fiscal_credit in fiscal_credits[:-1]:
            res[fiscal_credit] = (
                round(total * bases[fiscal_credit] / total_base, 2)
                if total_base
                else 0.0
            )
            pending -= res[fiscal_credit]
        res[fiscal_credits[-1]] = round(pending, 2)
        return res

    def _get_lines(self, cols, vat_cols):
        lines, c_taxes, retention_perception_summary = self._group_lines_data(
            cols, vat_cols
        )
        fiscal_credit_name = {
            'direct_taxed': 'Directo Gravado',
            'direct_exempt': 'Directo Exento',
            'apport': 'Prorrateable',
        }
        unassigned_fiscal_credit_name = _('Sin clasificar')

        by_fiscal_credit = {
            # TIENEN RELACIONADO IVA PERO TIENEN FISCAL_CREDIT = direct_taxed, apport, direct_exempt
            'direct_taxed': {
                '10.5%': [0.0, 0.0],
                '21.0%': [0.0, 0.0],
                '27.0%': [0.0, 0.0],
            },
            'apport': {
                '10.5%': [0.0, 0.0],
                '21.0%': [0.0, 0.0],
                '27.0%': [0.0, 0.0],
            },
            'direct_exempt': {
                '10.5%': [0.0, 0.0],
                '21.0%': [0.0, 0.0],
                '27.0%': [0.0, 0.0],
            },
            'direct_taxed_refund': {
                '10.5%': [0.0, 0.0],
                '21.0%': [0.0, 0.0],
                '27.0%': [0.0, 0.0],
            },
            'apport_refund': {
                '10.5%': [0.0, 0.0],
                '21.0%': [0.0, 0.0],
                '27.0%': [0.0, 0.0],
            },
            'direct_exempt_refund': {
                '10.5%': [0.0, 0.0],
                '21.0%': [0.0, 0.0],
                '27.0%': [0.0, 0.0],
            },
            # TIENEN RELACIONADO IVA EXENTO
            'Exento': 0.0,
            'Exento_refund': 0.0,
            # NO TIENEN RELACIONADO IVA
            'untaxed': 0.0,
            'untaxed_refund': 0.0,
            # NO TIENEN RELACIONADO IVA Y ADEMAS NO SON RESPONSABLES INSCRIPTOS
            'ni_nr_ex_mon': 0.0,
            'ni_nr_ex_mon_refund': 0.0,
        }
        new_lines = []
        totals = [0] * (
            len(cols) + 4
        )  # +4 for base_vat, vat, no_taxed and total
        totals_fc_nd = [0] * (
            len(cols) + 4
        )  # +4 for base_vat, vat, no_taxed and total
        totals_nc = [0] * (
            len(cols) + 4
        )  # +4 for base_vat, vat, no_taxed and total
        for line in lines.values():
            new_line = (
                [
                    line['date'],
                    line['partner_name'][:20],
                    line['partner_vat'],
                    line['invoice_type'],
                    line['invoice_number'],
                    line['no_taxed'],
                ]
                + line['taxes']
                + [
                    line['total'],
                ]
            )

            first_vat = True
            for tax_id, vat_values in line['vat_taxes'].items():
                vat_split = list(vat_values.keys())
                vat_split.remove('name')
                vat_amounts = self._split_vat_amount(line, tax_id, vat_values)
                for fiscal_credit in vat_split:
                    if not first_vat:
                        new_line = [''] * 5
                        new_line = new_line + (
                            [0] * (len(cols) + 2)
                        )  # +2 for no_taxed and total
                    base_vat_amount = vat_values[fiscal_credit]
                    vat_aliquot = vat_values['name']
                    vat_amount = vat_amounts[fiscal_credit]

                    new_line.insert(5, base_vat_amount)
                    new_line.insert(6, vat_aliquot)
                    new_line.insert(7, vat_amount)
                    new_line.insert(
                        8,
                        fiscal_credit_name.get(
                            fiscal_credit, unassigned_fiscal_credit_name
                        ),
                    )
                    new_lines.append(new_line)
                    first_vat = False

                    totals[0] += base_vat_amount
                    totals[1] += vat_amount
                    if fiscal_credit not in fiscal_credit_name:
                        _logger.warning(
                            "Skipping apportionable VAT fiscal credit summary "
                            "for invoice %s (%s): unexpected fiscal_credit=%r",
                            line['invoice_number'],
                            line['invoice_type'],
                            fiscal_credit,
                        )
                        continue
                    if line['invoice_type'].startswith('NC'):
                        totals_nc[0] += base_vat_amount
                        totals_nc[1] += vat_amount
                        fiscal_credit = fiscal_credit + '_refund'
                    else:
                        totals_fc_nd[0] += base_vat_amount
                        totals_fc_nd[1] += vat_amount

                    if vat_aliquot in ('Exento', 'Exento_refund'):
                        by_fiscal_credit[vat_aliquot] += base_vat_amount
                    else:
                        by_fiscal_credit[fiscal_credit][vat_aliquot][
                            0
                        ] += base_vat_amount
                        by_fiscal_credit[fiscal_credit][vat_aliquot][
                            1
                        ] += vat_amount

            by_fiscal_credit_untaxed_key = 'untaxed'
            if first_vat:
                # If this value is True, it is a no taxed invoice (maybe C type)
                new_line.insert(5, 0.0)
                new_line.insert(6, '')
                new_line.insert(7, 0.0)
                new_line.insert(8, '')
                new_lines.append(new_line)
                by_fiscal_credit_untaxed_key = 'ni_nr_ex_mon'

            for i, amount in enumerate(line['taxes']):
                i = (
                    i + 3
                )  # +3 for base_vat_amount, vat_amount and no_taxed_amount
                totals[i] += amount
                if line['invoice_type'].startswith('NC'):
                    totals_nc[i] += amount
                else:
                    totals_fc_nd[i] += amount

            totals[2] += line['no_taxed']
            totals[-1] += line['total']
            if line['invoice_type'].startswith('NC'):
                totals_nc[2] += line['no_taxed']
                totals_nc[-1] += line['total']
                by_fiscal_credit_untaxed_key = (
                    by_fiscal_credit_untaxed_key + '_refund'
                )
            else:
                totals_fc_nd[2] += line['no_taxed']
                totals_fc_nd[-1] += line['total']

            by_fiscal_credit[by_fiscal_credit_untaxed_key] += line['no_taxed']

        totals.insert(1, '')
        totals.insert(3, '')
        totals_nc.insert(1, '')
        totals_nc.insert(3, '')
        totals_fc_nd.insert(1, '')
        totals_fc_nd.insert(3, '')

        new_retention_perception_summary = []
        for line in retention_perception_summary.values():
            new_retention_perception_summary.append(
                [
                    line[0].get('es_AR', line[0].get('en_US', '')),
                    line[1],
                ]
            )

        for fiscal_type in (
            'direct_taxed',
            'apport',
            'direct_exempt',
            'direct_taxed_refund',
            'apport_refund',
            'direct_exempt_refund',
        ):
            aliquots = (
                by_fiscal_credit[fiscal_type]['10.5%'],
                by_fiscal_credit[fiscal_type]['21.0%'],
                by_fiscal_credit[fiscal_type]['27.0%'],
            )
            by_fiscal_credit[fiscal_type] = aliquots

        return (
            new_lines,
            totals,
            totals_fc_nd,
            totals_nc,
            c_taxes,
            new_retention_perception_summary,
            by_fiscal_credit,
        )

    def _get_line_vals(self):
        q = """
            SELECT
                i.invoice_date AS date,
                i.id AS invoice_id,
                i.name AS invoice_number,
                i.move_type AS invoice_type,
                i.denomination AS denomination,
                i.currency_id AS currency,
                i.amount_total AS invoice_total,
                vt.afip_code as voucher_type,
                l.id AS line_id,
                l.tax_line_id AS tax_line_id,
                l.credit AS credit,
                l.debit AS debit,
                l.fiscal_credit AS fiscal_credit,
                rp.id AS partner_id,
                afp.name AS fiscal_position,
                afp.id AS fpid,
                rp.name AS partner,
                rp.vat AS vat,
                amlatr.account_tax_id AS tax_ids
            FROM account_move_line l
            JOIN account_move i ON i.id = l.move_id
            JOIN res_voucher_type vt ON vt.id = i.voucher_type_id
            JOIN res_partner rp ON rp.id = i.partner_id
            JOIN account_account a ON a.id = l.account_id
            JOIN account_fiscal_position afp ON afp.id = i.fiscal_position_id
            LEFT JOIN account_move_line_account_tax_rel amlatr
            ON account_move_line_id = l.id
            INNER JOIN res_company lc
            ON i.company_id = lc.id
            WHERE i.move_type IN %(inv_type)s
                AND i.state = 'posted'
                AND
        """
        q += 'i.date' if self.based_on == 'purchase' else 'i.invoice_date'
        q += """
                BETWEEN %(date_from)s AND %(date_to)s
                AND a.account_type NOT LIKE '%%payable'
                AND a.account_type NOT LIKE '%%receivable'
                AND l.company_id = %(company_id)s
        ORDER BY date, invoice_type, invoice_number, line_id
        """
        q_vals = {
            'inv_type': tuple(self._get_move_types()),
            'company_id': self.company_id.id,
            'date_from': self.date_from,
            'date_to': self.date_to,
        }

        self._cr.execute(q, q_vals)

        # Obtenemos el resultado de la consulta
        return self._collapse_non_vat_lines(self._cr.dictfetchall())

    def _collapse_non_vat_lines(self, rows):
        """Product lines with taxes but no VAT (e.g. only perceptions) are
        not taxed: keep a single row without tax_ids so they count as
        No Gravado, like in the subjournal report."""
        tax_ids = {row['tax_ids'] for row in rows if row['tax_ids']}
        vat_ids = set(
            self.env['account.tax']
            .browse(tax_ids)
            .filtered(lambda t: t.tax_group_id.group_type == 'vat')
            .ids
        )
        line_taxes = defaultdict(set)
        for row in rows:
            if row['tax_ids'] and not row['tax_line_id']:
                line_taxes[row['line_id']].add(row['tax_ids'])
        non_vat_lines = {
            line_id
            for line_id, taxes in line_taxes.items()
            if not taxes & vat_ids
        }
        res = []
        seen = set()
        for row in rows:
            if row['line_id'] in non_vat_lines:
                if row['line_id'] in seen:
                    continue
                seen.add(row['line_id'])
                row = dict(row, tax_ids=None)
            res.append(row)
        return res

    def _get_tax_line_totals(self, group_type):
        """Amounts of the tax lines of the given tax group, taken from the
        same lines as the report detail.
        Returns {tax: [amount, refund_amount]}."""
        based_sign = -1 if self.based_on == 'purchase' else 1
        refund_types = ('out_refund', 'in_refund')
        lines = {}
        for row in self._get_line_vals():
            if row['tax_line_id']:
                lines[row['line_id']] = row
        taxes = (
            self.env['account.tax']
            .browse({row['tax_line_id'] for row in lines.values()})
            .filtered(lambda t: t.tax_group_id.group_type == group_type)
        )
        totals = {tax: [0.0, 0.0] for tax in taxes.sorted('sequence')}
        for row in lines.values():
            tax = taxes.browse(row['tax_line_id'])
            if tax not in totals:
                continue
            amount = (row['credit'] - row['debit']) * based_sign
            totals[tax][row['invoice_type'] in refund_types] += amount
        return totals

    def _get_taxes_vals(self):
        q = """
            SELECT
                amlatr.account_tax_id AS tax_id,
                atg.group_type,
                at.retention_type,
                at.is_exempt,
                at.name,
                at.amount
            FROM account_move_line l
            JOIN account_move i ON i.id = l.move_id
            LEFT JOIN account_move_line_account_tax_rel amlatr
            ON account_move_line_id = l.id
            LEFT JOIN account_tax at ON amlatr.account_tax_id = at.id
            LEFT JOIN account_tax_group atg ON atg.id = at.tax_group_id
            JOIN account_account a ON a.id = l.account_id
            WHERE i.move_type IN %(inv_type)s
                AND i.state = 'posted'
                AND
        """
        q += 'i.date' if self.based_on == 'purchase' else 'i.invoice_date'
        q += """
                BETWEEN %(date_from)s AND %(date_to)s
                AND a.account_type NOT LIKE '%%payable'
                AND a.account_type NOT LIKE '%%receivable'
                AND l.company_id = %(company_id)s
            GROUP BY tax_id, atg.group_type, at.retention_type, at.is_exempt, at.name, at.amount
        """
        q_vals = {
            'inv_type': tuple(self._get_move_types()),
            'company_id': self.company_id.id,
            'date_from': self.date_from,
            'date_to': self.date_to,
        }

        self._cr.execute(q, q_vals)

        # Obtenemos el resultado de la consulta
        return self._cr.dictfetchall()

    def _get_retention_data(self):
        retention_query = """
        SELECT ret.name, -1 * sum(r.amount), conc.code FROM account_payment_order_retention_line r
        JOIN account_tax ret ON r.retention_id = ret.id
        JOIN retention_concept conc ON r.concept_id = conc.id
        WHERE r.date BETWEEN %(date_start)s AND %(date_end)s
        AND ret.type_tax_use LIKE %(based_on)s
        AND r.company_id = %(company)s
        GROUP BY ret.id, conc.code
        """
        vals = {
            'based_on': self.based_on,
            'date_start': self.date_from,
            'date_end': self.date_to,
            'company': self.company_id.id,
        }
        self.env.cr.execute(retention_query, vals)
        retention_res = self.env.cr.fetchall()
        return retention_res

    def _get_perception_data(self):
        # Same source as the detail columns (accounting date, company
        # currency) so the totals match
        return [
            ({'es_AR': tax.with_context(lang='es_AR').name}, sum(amounts))
            for tax, amounts in self._get_tax_line_totals('perception').items()
        ]

    def _parse_retention_perception(self):
        taxes_data_parsed = []
        taxes_data = self._get_retention_data()
        for line in taxes_data:
            taxes_data_parsed.append(
                (
                    line[0].get('es_AR', line[0].get('en_US', 'No name')),
                    line[1],
                    line[2],
                )
            )
        taxes_data = self._get_perception_data()
        for line in taxes_data:
            taxes_data_parsed.append(
                (
                    line[0].get('es_AR', line[0].get('en_US', 'No name')),
                    line[1],
                    '',
                )
            )
        return taxes_data_parsed

    def run(self):
        self._do_validations()

        cols, vat_cols = self._get_columns()
        (
            invoice_lines,
            totals,
            totals_fc_nd,
            totals_nc,
            c_taxes,
            retention_perception_summary,
            apportionable_vat_data,
        ) = self._get_lines(cols, vat_cols)

        invoice_list_header = [
            'Neto Grav.',
            '%',
            'IVA',
            'Asig.CF',
            'No Gravado',
        ]
        for i, col in enumerate(cols):
            if c_taxes[i] > 0:
                invoice_list_header.append(_clean_tax_name(col['name']))
        invoice_list_header.append('Total')

        retention_perception = self._parse_retention_perception()
        perception_total = sum(
            sum(amounts)
            for amounts in self._get_tax_line_totals('perception').values()
        )
        internal_taxes = [0.0, 0.0]
        for amounts in self._get_tax_line_totals('internals').values():
            internal_taxes[0] += amounts[0]
            internal_taxes[1] += amounts[1]

        return self.env.ref(
            'l10n_ar_eynes.action_report_report_subjournal_apportionable_vat'
        ).report_action(
            self,
            data={
                'options': [],
                'title': self._get_title(),
                'invoice_list_header': invoice_list_header,
                'invoice_lines': invoice_lines,
                'totals': totals,
                'totals_fc_nd': totals_fc_nd,
                'totals_nc': totals_nc,
                'retention_perception_summary': retention_perception_summary,
                'first_block_apportionable_vat_title': self._get_apport_block_title(
                    'first'
                ),
                'second_block_apportionable_vat_title': self._get_apport_block_title(
                    'second'
                ),
                'direct_taxed': apportionable_vat_data['direct_taxed'],
                'apport': apportionable_vat_data['apport'],
                'direct_exempt': apportionable_vat_data['direct_exempt'],
                'direct_taxed_refund': apportionable_vat_data[
                    'direct_taxed_refund'
                ],
                'apport_refund': apportionable_vat_data['apport_refund'],
                'direct_exempt_refund': apportionable_vat_data[
                    'direct_exempt_refund'
                ],
                'exempt': apportionable_vat_data['Exento'],
                'untaxed': apportionable_vat_data['untaxed'],
                'ni_nr_ex_mon': apportionable_vat_data['ni_nr_ex_mon'],
                'exempt_refund': apportionable_vat_data['Exento_refund'],
                'untaxed_refund': apportionable_vat_data['untaxed_refund'],
                'ni_nr_ex_mon_refund': apportionable_vat_data[
                    'ni_nr_ex_mon_refund'
                ],
                'retention_perception': retention_perception,
                'perception_total': perception_total,
                'cero': 0.0,
                'fees': 0.0,
                'internal_taxes': internal_taxes[0],
                'cero_refund': 0.0,
                'fees_refund': 0.0,
                'internal_taxes_refund': internal_taxes[1],
            },
        )
