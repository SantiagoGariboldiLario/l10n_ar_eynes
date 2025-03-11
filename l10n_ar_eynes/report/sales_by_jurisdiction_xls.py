from datetime import datetime

from odoo import _, models

from odoo.addons.report_xlsx_helper.report.report_xlsx_format import (
    FORMATS,
    XLS_HEADERS,
)


class SalesExportXlsx(models.AbstractModel):
    _name = 'report.l10n_ar_eynes.sales_by_jurisdiction_export_xlsx'
    _inherit = 'report.report_xlsx.abstract'

    def _get_cell_format(self, wb):
        cell_format = wb.add_format()
        cell_format.set_align("right")
        cell_format.set_num_format = "#,##0.00"
        return cell_format

    def _get_formula_format(self, wb):
        formula_format = wb.add_format()
        formula_format.set_bold()
        formula_format.set_bg_color('#FFFFCC')
        formula_format.set_align("right")
        formula_format.set_num_format = "#.##0,00"
        return formula_format

    def _get_ws_params(self, wb, data, lines):
        sales_template = {
            'fecha': {
                'header': {
                    'value': 'Fecha',
                },
                'data': {
                    'value': self._render("line['fecha']"),
                },
                'width': 20,
            },
            'factura': {
                'header': {
                    'value': 'Factura',
                },
                'data': {
                    'value': self._render("line['invoice_internal_number']"),
                },
                'width': 20,
            },
            'fecha_asiento': {
                'header': {
                    'value': 'Fecha asiento',
                },
                'data': {
                    'value': self._render("line['fecha_asiento']"),
                },
                'width': 20,
            },
            'nombre_cliente': {
                'header': {
                    'value': 'Nombre cliente',
                },
                'data': {
                    'value': self._render("line['nombre_cliente']"),
                },
                'width': 20,
            },
            'jurisdiccion': {
                'header': {
                    'value': 'Jurisdicción',
                },
                'data': {
                    'value': self._render("line['jurisdiccion']"),
                },
                'width': 20,
            },
            'cp': {
                'header': {
                    'value': 'Código Postal',
                },
                'data': {
                    'value': self._render("line['cp']"),
                },
                'width': 20,
            },
            'codigo_cuenta': {
                'header': {
                    'value': 'Código cuenta',
                },
                'data': {
                    'value': self._render("line['codigo_cuenta']"),
                },
                'width': 20,
            },
            'nombre_cuenta_contable': {
                'header': {
                    'value': 'Nombre cuenta contable',
                },
                'data': {
                    'value': self._render("line['nombre_cuenta_contable']"),
                },
                'width': 22,
            },
            'monto': {
                'header': {
                    'value': 'Monto',
                },
                'data': {
                    'value': self._render("line['monto']"),
                    'format': self._get_cell_format(wb),
                },
                'width': 20,
            },
        }

        wanted_list = [
            'fecha',
            'factura',
            'fecha_asiento',
            'nombre_cliente',
            'jurisdiccion',
            'cp',
            'codigo_cuenta',
            'nombre_cuenta_contable',
            'monto',
        ]
        worksheets = []
        company_ids = self.env['res.company'].browse(data['company_ids'])
        for company_id in company_ids:
            report_type = data['report_type']
            title = (
                _("Sales by jurisdiction")
                if report_type == 'sale'
                else _("Purchases by jurisdiction")
            )
            ws_params = {
                'company_id': company_id.id,
                'ws_name': company_id.name,
                'generate_ws_method': '_sales_report',
                'title': company_id.name + " " + title,
                'wanted_list': wanted_list,
                'col_specs': sales_template,
                'report_type': report_type,
            }
            worksheets.append(ws_params)

        return worksheets

    def _print_jurisdiction_block(
        self, wb, ws, row_pos, ws_params, jurisdiction, lines
    ):
        row_pos += 1
        jurisdiction = jurisdiction or _("Undefined")
        ws.merge_range(
            row_pos,
            0,
            row_pos,
            len(ws_params['col_specs']) - 1,
            jurisdiction,
            FORMATS["format_theader_yellow_left"],
        )
        row_pos += 1
        _from = row_pos
        jurisdiction_total = 0
        for line in lines:
            line['nombre_cuenta_contable'] = line['nombre_cuenta_contable'][
                self.env.user.lang
            ]
            # Change date format to dd-mm-yyyy
            line['fecha'] = (
                datetime.strftime(line['fecha'], "%d-%m-%Y")
                if line['fecha']
                else ''
            )
            line['fecha_asiento'] = (
                datetime.strftime(line['fecha_asiento'], "%d-%m-%Y")
                if line['fecha_asiento']
                else ''
            )
            line['monto'] = float(line['monto'])
            row_pos = self._write_line(
                ws,
                row_pos,
                ws_params,
                col_specs_section='data',
                render_space={
                    'line': line,
                },
                default_format=FORMATS["format_tcell_left"],
            )
            jurisdiction_total += line['monto']

        ws.merge_range(
            row_pos,
            0,
            row_pos,
            len(ws_params['col_specs']) - 2,
            _("Totals") + ': [%s]' % jurisdiction,
            FORMATS["format_theader_yellow_left"],
        )
        formula = '=SUM(I{_from}:I{to}'.format(_from=_from, to=row_pos)
        ws.write_formula(
            row_pos,
            len(ws_params['col_specs']) - 1,
            formula,
            self._get_formula_format(wb),
            round(jurisdiction_total, 2),
        )
        return (_from, row_pos, jurisdiction_total)

    def _sales_report(self, workbook, ws, ws_params, data, lines):
        lines = self.get_data(
            data, ws_params['company_id'], ws_params['report_type']
        )
        ws.set_portrait()
        ws.fit_to_pages(1, 0)
        ws.set_header(XLS_HEADERS["xls_headers"]["standard"])
        ws.set_footer(XLS_HEADERS["xls_footers"]["standard"])

        self._set_column_width(ws, ws_params)

        row_pos = 0
        row_pos = self._write_ws_title(ws, row_pos, ws_params)
        row_pos = self._write_line(
            ws,
            row_pos,
            ws_params,
            col_specs_section='header',
            default_format=FORMATS["format_theader_yellow_left"],
        )
        ws.freeze_panes(row_pos, 0)

        lines_by_jurisdictions = {}

        for line in lines:
            jurisdiction = line.get('jurisdiccion')
            lines_by_jurisdictions.setdefault(jurisdiction, [])
            lines_by_jurisdictions[jurisdiction].append(line)

        grand_total = 0
        block_info = []
        for jurisdiction, lines in lines_by_jurisdictions.items():
            init_row, row_pos, block_total = self._print_jurisdiction_block(
                workbook, ws, row_pos, ws_params, jurisdiction, lines
            )
            grand_total += block_total
            block_info.append((init_row, row_pos))
            row_pos += 1

        formula_row = row_pos + 1

        total_formula = "=" + " + ".join(
            map(lambda block: "SUM(I%s:I%s)" % (block[0], block[1]), block_info)
        )

        row_pos = self._write_line(
            ws,
            row_pos,
            ws_params,
            col_specs_section='footer',
            default_format=FORMATS["format_theader_yellow_left"],
        )
        row_pos = self._write_line(
            ws,
            row_pos,
            ws_params,
            col_specs_section='footer',
            default_format=FORMATS["format_theader_yellow_left"],
        )
        ws.write(
            formula_row, 0, _("Totals"), FORMATS["format_theader_yellow_left"]
        )
        ws.write_formula(
            formula_row,
            len(ws_params['col_specs']) - 1,
            total_formula,
            self._get_formula_format(workbook),
            round(grand_total, 2),
        )

    def get_data(self, data, company, report_type):
        select_extra, join_extra, where_extra, sort_selection = self.env[
            'account.move'
        ]._report_xls_query_extra()

        # SQL select for performance reasons, as a consequence, there are no
        # field value translations.
        # If performance is no issue, you can adapt the _report_xls_template in
        # an inherited module to add field value translations.
        invoice_number_field = (
            'ai.internal_number'
            if report_type == 'sale'
            else 'ai.supplier_move_reference'
        )
        query = (
            """
        SELECT
            ai.id AS invoice_id,
            CASE
                WHEN ai.is_debit_note IS True THEN 'ND '
                WHEN ai.move_type = 'out_invoice' THEN 'FAC '
                WHEN ai.move_type = 'in_invoice' THEN 'FAC '
                ELSE 'NC ' END || UPPER(ai.denomination) || ' ' ||
                """
            + invoice_number_field
            + """ AS invoice_internal_number,
            ai.company_id AS company_id,
            rc.name AS company_name,
            ai.invoice_date AS Fecha,
            ai.denomination AS Denom,
            pa.name AS Pto_Vta,
            """
            + invoice_number_field
            + """ AS Num_Factura,
            ai.date AS Fecha_Asiento,
            rp.name AS Nombre_Cliente,
            COALESCE(rcs2.name, rcs.name, rcs_def.name) AS Jurisdiccion,
            rp.zip AS CP,
            aa.code AS Codigo_Cuenta,
            aa.name AS Nombre_Cuenta_Contable,
            (%(sign)s * ail.balance) AS Monto,
        CASE
            WHEN ai.is_debit_note IS True THEN 'Nota de Débito'
            WHEN ai.move_type = 'out_invoice' THEN 'Factura'
            WHEN ai.move_type = 'in_invoice' THEN 'Factura'
            ELSE 'Nota de Crédito' END AS TipoFactura
        """
            + select_extra
            + """
        FROM account_move_line ail
        LEFT JOIN product_product pp
            ON pp.id = ail.product_id
        JOIN account_account aa
            ON aa.id = ail.account_id
        JOIN account_move ai
                ON ai.id = ail.move_id
        LEFT JOIN res_partner rp2
            ON ai.partner_shipping_id = rp2.id
        JOIN res_company rc
            ON rc.id = ai.company_id
        LEFT JOIN res_partner rp
            ON rp.id = ai.partner_id
        LEFT JOIN res_country_state rcs
            ON rcs.id = rp.state_id
        LEFT JOIN res_country_state rcs2
            ON rcs2.id = rp2.state_id
        JOIN account_journal pa
            ON pa.id = ai.journal_id
        LEFT JOIN report_default_jurisdiction_configuration rdjc
            ON rdjc.pos_ar_id = pa.id
        LEFT JOIN res_country_state rcs_def
            ON rcs_def.id = rdjc.state_id
        """
            + join_extra
            + """
        WHERE ai.invoice_date BETWEEN %(date_start)s AND %(date_stop)s
            AND ai.company_id = %(company_id)s
            AND ai.state = 'posted'
            AND ai.move_type IN %(move_type)s
            AND ail.display_type = 'product'
        """
            + where_extra
            + """
        ORDER BY """
            + sort_selection
            + """
        rcs.name, ai.invoice_date,
        """
            + invoice_number_field
        )
        query_vals = {
            'date_start': data['date_start'],
            'date_stop': data['date_stop'],
            'company_id': company,
            'move_type': ('out_invoice', 'out_refund')
            if report_type == 'sale'
            else ('in_invoice', 'in_refund'),
            'sign': -1 if report_type == 'sale' else 1,
        }
        self._cr.execute(query, query_vals)
        lines = self._cr.dictfetchall()

        return lines
