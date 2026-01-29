##############################################################################
#
#   Copyright (c) 2022-2023 Eynes SRL  (Eynes - Ingenieria del software)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
#
##############################################################################
import logging
from string import ascii_uppercase

from odoo import _, models
from odoo.exceptions import UserError

logger = logging.getLogger(__name__)


def int2xlscol(number, state=None):
    if state is None:
        state = []
    alpsize = ascii_uppercase.__len__()
    q, r = divmod(number, alpsize)
    if q == 0:
        state.append(ascii_uppercase[r])
        return ''.join(reversed(state))
    state.append(ascii_uppercase[r])
    state = int2xlscol(q - 1, state)
    return state


class SubjournalXlsx(models.AbstractModel):
    _name = 'report.report_xlsx.move_line_list_subj'
    _inherit = 'report.report_xlsx.abstract'

    def get_title(self, obj):
        if obj.based_on == 'sale':
            sub_type = 'Ventas'
        else:
            sub_type = 'Compras'

        title = 'Reporte - IVA %s Periodo %s a %s' % (
            sub_type,
            obj.date_from,
            obj.date_to,
        )
        return title

    def _get_types(self, obj):
        if obj.based_on == 'sale':
            return ['out_invoice', 'out_refund', 'out_debit']
        else:
            return ['in_invoice', 'in_refund', 'in_debit']

    def get_invoice_type(self, inv_type, denom, is_debit):
        fiscal_type = "F"
        if inv_type in ('out_refund', 'in_refund'):
            fiscal_type = "NC"
        elif is_debit:
            fiscal_type = "ND"
        return '%s %s' % (fiscal_type, denom.upper())

    def get_columns(self, types, obj):
        taxes = self._get_taxes_vals(types, obj)
        all_taxes = []
        i = 0
        base_first = obj.base_position == 'first'

        already_vat = False
        already_gross = False
        already_income = False

        for tax in taxes:
            tax_id = tax.get('tax_id', False)
            if tax_id:
                retention_type = tax.get('retention_type', '')
                if obj.perception_retention_grouped and retention_type in [
                    'gross_income',
                    'vat',
                    'profit',
                ]:
                    if retention_type == 'gross_income' and not already_gross:
                        already_gross = True
                        gross_vals = {
                            'id': False,
                            'ids': [
                                t.get('tax_id', False)
                                for t in taxes
                                if t.get('retention_type', '') == 'gross_income'
                            ],
                            'names': [
                                t.get('name', '')
                                for t in taxes
                                if t.get('retention_type', '') == 'gross_income'
                            ],
                            'is_exempt': tax.get('is_exempt', False),
                            'name': 'Retenciones / Percepciones IIBB',
                            'type': 'gross_income',
                            'column': 7 + i,
                        }
                        i += 1
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
                            'column': 7 + i,
                        }
                        i += 1
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
                            'column': 7 + i,
                        }
                        i += 1
                        all_taxes.append(income_vals)
                    continue

                name = tax.get('name', '')
                name = name.get('es_AR', name.get('en_US', '')) if name else ''
                if (tax.get('group_type', '') == 'vat') and base_first:
                    base_vals = {
                        'id': tax_id,
                        'is_exempt': tax.get('is_exempt', False),
                        'name': 'Base ' + name,
                        'type': 'base',
                        'column': 7 + i,
                    }
                    all_taxes.append(base_vals)
                    i += 1

                tax_vals = {
                    'id': tax_id,
                    'is_exempt': tax.get('is_exempt', False),
                    'name': name,
                    'type': 'tax',
                    'column': 7 + i,
                }
                all_taxes.append(tax_vals)
                i += 1

                if (tax.get('group_type', '') == 'vat') and not base_first:
                    base_vals = {
                        'id': tax_id,
                        'is_exempt': tax.get('is_exempt', False),
                        'name': 'Base ' + name,
                        'type': 'base',
                        'column': 7 + i,
                    }
                    all_taxes.append(base_vals)
                    i += 1
        return all_taxes

    def get_lines(self, types, obj, cols):
        query_vals = self._get_line_vals(types, obj)
        if not len(query_vals):
            raise UserError(_('There were no moves for this period'))

        c_taxes = [0] * len(cols)
        final_consumer_id = self.env.ref('l10n_ar_eynes.fiscal_position_cf').id

        lines = {}
        retention_perception_summary = {}
        lines_quantity = len(query_vals)
        current_invoice_accum = 0.0
        for il, line in enumerate(query_vals):
            if il == 0 or query_vals[il-1]['invoice_id'] != line['invoice_id']:
                current_invoice_accum = 0.0

            next_line_index = il + 1
            next_line = (
                query_vals[next_line_index]
                if next_line_index < lines_quantity
                else None
            )
            next_line_invoice_id = next_line['invoice_id'] if next_line else -1
            is_final_consumer = line['fpid'] == final_consumer_id
            based_sign = 1
            if obj.based_on == 'purchase':
                based_sign = -1
            invoice_type = self.get_invoice_type(
                line['invoice_type'],
                line['denomination'],
                line['is_debit_note'],
            )
            key = line['invoice_id']
            # line['line_id']
            amount = (line['credit'] - line['debit']) * based_sign
            current_invoice_accum += amount

            if (
                obj.grouped
                and is_final_consumer
                and line['invoice_total'] < obj.grouped_max_amount
            ):
                key = 'cf' + line['date'].strftime('%d/%m/%Y') + invoice_type
                lines.setdefault(
                    key,
                    {
                        'invoice_number': '',
                        'date': line['date'],
                        'invoice_type': invoice_type,
                        'partner_name': 'Agrupado CF monto menor a %s'
                        % round(obj.grouped_max_amount, 2),
                        'partner_vat': '',
                        'province': '',
                        'partner_fiscal_pos': line['fiscal_position'],
                        'total': 0.0,
                        'taxes': [0] * len(cols),
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
                        'province': line['state'],
                        'partner_fiscal_pos': line['fiscal_position'],
                        'total': 0.0,
                        'taxes': [0] * len(cols),
                        'no_taxed': 0.0,
                    },
                )

            for i, tax in enumerate(cols):
                if obj.perception_retention_grouped:
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

            if next_line_invoice_id != line['invoice_id']:
                invoice_total = (
                    line['invoice_total']
                    if current_invoice_accum > 0
                    else (-1 * line['invoice_total'])
                )
                lines[key]['total'] = invoice_total
                lines[key]['no_taxed'] = round(
                    invoice_total - sum(lines[key]['taxes']), 2
                )

        return lines, c_taxes, retention_perception_summary

    def _get_line_vals(self, types, obj):
        q = """
            SELECT
                i.invoice_date AS date,
                i.id AS invoice_id,
                i.name AS invoice_number,
                i.move_type AS invoice_type,
                i.cae AS cae,
                i.cae_due_date AS cae_due_date,
                i.is_debit_note AS is_debit_note,
                i.denomination AS denomination,
                i.currency_id AS currency,
                i.amount_total AS invoice_total,
                l.id AS line_id,
                l.tax_line_id AS tax_line_id,
                l.credit AS credit,
                l.debit AS debit,
                p.id AS partner_id,
                afp.name AS fiscal_position,
                afp.id AS fpid,
                rp.name AS partner,
                rp.vat AS vat,
                rcs.name AS state,
                amlatr.account_tax_id AS tax_ids
            FROM account_move_line l
            JOIN account_move i ON i.id = l.move_id
            JOIN res_partner rp ON rp.id = i.partner_id
            LEFT JOIN res_country_state rcs ON rcs.id = rp.state_id
            JOIN res_partner p ON p.id = i.partner_id
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
        q += 'i.date' if obj.based_on == 'purchase' else 'i.invoice_date'
        q += """
                BETWEEN %(date_from)s AND %(date_to)s
                AND a.account_type NOT LIKE '%%payable'
                AND a.account_type NOT LIKE '%%receivable'
                AND l.company_id = %(company_id)s
        ORDER BY date, invoice_type, is_debit_note, invoice_number, line_id
        """
        q_vals = {
            'inv_type': tuple(types),
            'company_id': obj.company_id.id,
            'date_from': obj.date_from,
            'date_to': obj.date_to,
            'grouped': obj.grouped,
            'grouped_max': obj.grouped_max_amount,
            'fiscal_id': self.env.ref('l10n_ar_eynes.fiscal_position_cf').id,
        }

        self._cr.execute(q, q_vals)

        # Obtenemos el resultado de la consulta
        return self._cr.dictfetchall()

    def _get_taxes_vals(self, types, obj):
        """ """

        q = """
            SELECT
                amlatr.account_tax_id AS tax_id,
                atg.group_type,
                at.retention_type,
                at.is_exempt,
                at.name
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
        q += 'i.date' if obj.based_on == 'purchase' else 'i.invoice_date'
        q += """
                BETWEEN %(date_from)s AND %(date_to)s
                AND a.account_type NOT LIKE '%%payable'
                AND a.account_type NOT LIKE '%%receivable'
                AND l.company_id = %(company_id)s
            GROUP BY tax_id, atg.group_type, at.retention_type, at.is_exempt, at.name
        """
        q_vals = {
            'inv_type': tuple(types),
            'company_id': obj.company_id.id,
            'date_from': obj.date_from,
            'date_to': obj.date_to,
        }

        self._cr.execute(q, q_vals)

        # Obtenemos el resultado de la consulta
        return self._cr.dictfetchall()

    def _report_xls_fields(self):
        base_lst = [
            'Fecha',
            'Compañía',
            'Razon Social',
            'Provincia',
            'CUIT',
            'Cond. IVA',
            'Tipo',
            'Numero',
            'No Gravado',
            'Total',
        ]
        config_obj = self.env['ir.config_parameter']
        config_param = config_obj.sudo().get_param('subjournal_export_cae')
        if config_param:
            base_lst.insert(6, 'cae')
            base_lst.insert(7, 'cae_due_date')
        return base_lst

    def set_column(self, worksheet, index):
        worksheet.set_column('A:A', 10)
        worksheet.set_column('B:C', 20)
        worksheet.set_column('D:E', 10)
        worksheet.set_column('F:F', 5)
        worksheet.set_column('G:G', 10)
        worksheet.set_column('G:' + int2xlscol(index), 10)

    def create_format(
        self, workbook, bold, border_type, border_color, back_color
    ):
        _format = workbook.add_format(
            {
                'bold': bold,
                'bg_color': back_color,
                'font_size': 10,
                'font_name': 'Arial',
            }
        )
        _format.set_bottom(border_type)
        _format.set_bottom_color(border_color)
        _format.set_top(border_type)
        _format.set_top_color(border_color)
        _format.set_left(border_type)
        _format.set_left_color(border_color)
        _format.set_right(border_type)
        _format.set_right_color(border_color)
        return _format

    def generate_xlsx_report(self, workbook, data, obj):
        # Formats
        head_format = self.create_format(
            workbook, True, 1, '#C0C0C0', '#ffffb3'
        )
        date_format = self.create_format(
            workbook, False, 1, '#C0C0C0', '#ffffff'
        )
        gray_format = self.create_format(
            workbook, False, 1, '#C0C0C0', '#eaeaea'
        )
        footer_format = self.create_format(
            workbook, True, 1, '#C0C0C0', '#ffd6cc'
        )

        wizard_obj = self.env['account.tax.subjournal'].browse(obj.id)
        types = self._get_types(wizard_obj)
        wanted_list = self._report_xls_fields()
        title = self.get_title(wizard_obj)
        cols = self.get_columns(types, wizard_obj)
        lines, c_taxes, retention_perception_summary = self.get_lines(
            types, wizard_obj, cols
        )

        for i, col in enumerate(cols):
            if c_taxes[i] > 0:
                wanted_list.insert(-2, col['name'])
        sheet = workbook.add_worksheet(title)
        sheet.set_column('A:L', 23)
        starting_row = 4

        # Writing company, period and type
        vat_book_type = {
            'sale': 'LIBRO IVA VENTAS',
            'purchase': 'LIBRO IVA COMPRAS',
        }
        company_data = [
            ('A1', 'Razon Social', date_format),
            ('B1', wizard_obj.company_id.name, date_format),
            ('A2', vat_book_type[wizard_obj.based_on], date_format),
            ('A3', 'Perido', date_format),
            ('B3', wizard_obj.date_from.strftime('%m/%Y'), date_format),
        ]

        for data in company_data:
            sheet.write(data[0], data[1], data[2])

        # Writing Headers
        for i, column in enumerate(wanted_list):
            sheet.write(int2xlscol(i) + str(starting_row), column, head_format)
        self.set_column(sheet, i)

        # Insert values
        for p, invoice_id in enumerate(lines, start=starting_row + 1):
            line = lines[invoice_id]
            cell_format = gray_format
            if p % 2:
                cell_format = date_format
            sheet.write(
                'A' + str(p),
                line['date'].strftime('%d/%m/%Y'),
                cell_format,
            )
            sheet.write('B' + str(p), wizard_obj.company_id.name, cell_format)
            sheet.write('C' + str(p), line['partner_name'], cell_format)
            sheet.write('D' + str(p), line['province'], cell_format)
            sheet.write('E' + str(p), line['partner_vat'], cell_format)
            sheet.write(
                'F' + str(p),
                (
                    line['partner_fiscal_pos'][self.env.lang]
                    if self.env.lang in line['partner_fiscal_pos']
                    else line['partner_fiscal_pos']['en_US']
                ),
                cell_format,
            )
            sheet.write('G' + str(p), line['invoice_type'], cell_format)
            sheet.write('H' + str(p), line['invoice_number'], cell_format)
            i = 8
            for t, _tax in enumerate(cols):
                if c_taxes[t] > 0:
                    sheet.write(
                        int2xlscol(i) + str(p), line['taxes'][t], cell_format
                    )
                    i += 1
            sheet.write(int2xlscol(i) + str(p), line['no_taxed'], cell_format)
            sheet.write(int2xlscol(i + 1) + str(p), line['total'], cell_format)

        # Formulas
        fac_formula = '{=SUMIF(G2:G%(last_line)s,"F *",%(col)s2:%(col)s%(last_line)s) + SUMIF(G2:G%(last_line)s,"ND *",%(col)s2:%(col)s%(last_line)s)}'  # noqa
        nc_formula = '{=SUMIF(G2:G%(last_line)s,"NC *",%(col)s2:%(col)s%(last_line)s)}'  # noqa
        total_formula = '{=SUM(%(col)s2:%(col)s%(last_line)s)}'  # noqa

        last_row_num = len(lines) + starting_row
        last_row_char = str(last_row_num)
        fac_row_char = str(last_row_num + 3)
        nc_row_char = str(last_row_num + 4)
        total_row_char = str(last_row_num + 5)

        i = -1
        for j, col in enumerate(cols):
            if c_taxes[j] > 0:
                col_char = int2xlscol(col['column'] - i)
                indexes = {
                    'last_line': last_row_char,
                    'col': col_char,
                }

                # Fac
                sheet.write_formula(
                    col_char + fac_row_char,
                    fac_formula % indexes,
                    footer_format,
                )
                # NC
                sheet.write_formula(
                    col_char + nc_row_char,
                    nc_formula % indexes,
                    footer_format,
                )
                # Totals
                sheet.write_formula(
                    col_char + total_row_char,
                    total_formula % indexes,
                    footer_format,
                )
            else:
                i += 1

        ng_col_char = int2xlscol(7 + len(cols) - i)
        tot_col_char = int2xlscol(8 + len(cols) - i)

        indexes = {
            'last_line': last_row_char,
        }
        indexes.update({'col': ng_col_char})

        # Fac NoGravado
        sheet.write_formula(
            ng_col_char + fac_row_char,
            fac_formula % indexes,
            footer_format,
        )
        # NC NoGravado
        sheet.write_formula(
            ng_col_char + nc_row_char,
            nc_formula % indexes,
            footer_format,
        )
        # Total NoGravado
        sheet.write_formula(
            ng_col_char + total_row_char,
            total_formula % indexes,
            footer_format,
        )

        indexes.update({'col': tot_col_char})
        # Fac Total
        sheet.write_formula(
            tot_col_char + fac_row_char,
            fac_formula % indexes,
            footer_format,
        )
        # NC Total
        sheet.write_formula(
            tot_col_char + nc_row_char,
            nc_formula % indexes,
            footer_format,
        )
        # Total Final
        sheet.write_formula(
            tot_col_char + total_row_char,
            total_formula % indexes,
            footer_format,
        )

        keyval_row = last_row_num + 6
        for _key, val in retention_perception_summary.items():
            key_col = int2xlscol(8 + len(cols) - i - 1)
            val_col = int2xlscol(8 + len(cols) - i)
            keyval_row = keyval_row + 1
            sheet.write(
                key_col + str(keyval_row),
                (
                    val[0][self.env.lang]
                    if self.env.lang in val[0]
                    else val[0]['en_US']
                ),
            )
            sheet.write(val_col + str(keyval_row), val[1])

        # formula labels
        sheet.write('A' + fac_row_char, 'Subtotal FC/ND', footer_format)
        sheet.write('A' + nc_row_char, 'Subtotal NC', footer_format)
        sheet.write('A' + total_row_char, 'Total', footer_format)
        # Footer format
        indexes = {
            'fac_row': fac_row_char,
            'last_col': tot_col_char,
            'last_row': total_row_char,
        }
        c_range = 'A%(fac_row)s:%(last_col)s%(last_row)s'
        sheet.conditional_format(
            c_range % indexes,
            {
                'type': 'cell',
                'criteria': '=',
                'value': 0,
                'format': footer_format,
            },
        )
