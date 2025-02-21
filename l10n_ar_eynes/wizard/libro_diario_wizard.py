import json
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class JournalLedgerWizard(models.TransientModel):
    _name = 'journal.ledger.wizard'
    _description = 'Journal Ledger Wizard'

    company_id = fields.Many2one('res.company', 'Company', required=True)
    company_id_domain = fields.Char(
        default=lambda self: self._default_company_ids()
    )
    date_start = fields.Date(required=True)
    date_end = fields.Date(required=True)

    @api.model
    def _default_company_ids(self):
        return json.dumps(
            [('id', 'in', self.env.context.get('allowed_company_ids', []))]
        )

    def _get_data(self):
        query = """
        SELECT
            am.date AS Move_date,
            aa.code AS Move_line_account_code,
            aa.name AS Move_line_account_name,
            SUM(aml.debit) AS Move_line_debit,
            SUM(aml.credit) AS Move_line_credit,
            am.is_opening AS Openning,
            am.is_closing AS Closing
        FROM account_move am
        JOIN account_move_line aml
            ON am.id = aml.move_id
        JOIN account_account aa
            ON aml.account_id = aa.id
        WHERE
            am.state = 'posted' AND
            am.date >= %(date_start)s AND
            am.date <= %(date_end)s AND
            am.company_id = %(company)s
        GROUP BY
            am.date,
            am.is_opening,
            am.is_closing,
            aa.code,
            aa.name
        ORDER BY am.date, am.is_opening desc, am.is_closing
        """
        vals = {
            'date_start': self.date_start,
            'date_end': self.date_end,
            'company': self.company_id.id,
        }
        self.env.cr.execute(query, vals)
        res = self.env.cr.fetchall()
        return res

    def _get_move_headers(self, nro_asiento, fecha):
        return ['move_header', nro_asiento, fecha, '', '', 0.0, 0.0, 0.0, 0.0]

    def run(self):
        """
        Crea una matriz con los datos necesarios para crear la tabla de asientos
        [
            ['tipo_linea', 'nro_asiento', 'fecha', 'cod_cuenta', 'cuenta', 'debe', 'haber', 'total_debe', 'total_haber']
        ]

        tipo_linea:
            - move_header -> Genera el encabezado de asiento por día
                ['move_header', '1', '1/01/2024', '', '', 0.0, 0.0, 0.0, 0.0]
            - header -> Genera el encabezado de la tabla
                ['header', '', 'Fecha', 'Cod.cuenta', 'Cuenta', 'Debe', 'Haber', '', '']
            - body -> Representa una línea de apunte contable
                ['body', '1', '1/01/2024', '1.0.1.0.6', 'Deudores por ventas', 0.0, 1265.21, 0.0, 0.0]
                ['body', '1', '1/01/2024', '5.0.2.0.4', 'Insumos', 1265.21, 0.0, 0.0, 0.0]
            - footer -> Genera los totales por día
                ['footer', '1', '', '', '', 0.0, 0.0, 1265.21, 1265.21]
        """
        data = self._get_data()

        move_headers = []
        moves = []

        last_date = ''
        last_special = False
        nro_asiento = 0
        footer = None
        for line in data:
            date = line[0].strftime("%d/%m/%Y")
            is_special = line[5] or line[6]
            if date != last_date or is_special != last_special:
                # **Primer asiento del dia**
                # Incrementamos el número de asiento:
                nro_asiento += 1
                # Guardamos el dato de la última fecha procesada para no ingresar en esta condición:
                last_date = date
                # Guardamos si es linea de cierre/apertura o no:
                last_special = is_special
                # Generamos encabezado:
                move_headers.append(self._get_move_headers(nro_asiento, date))
                if footer:
                    # El footer se inicializa en None para evitar appendearlo al ingresar por primera vez en
                    # esta condición de 'primer asiento de día'
                    moves.append(footer)
                # Reseteamos los totales:
                footer = [
                    'footer',
                    nro_asiento,
                    date,
                    '',
                    '',
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                ]
            moves.append(
                [
                    'body',
                    nro_asiento,
                    date,
                    line[1],
                    line[2].get(
                        'es_AR', line[2].get('en_US', '')
                    ),  # Primero intenta 'es_AR', luego 'en_US', si no hay ninguno, usa ''
                    line[3],
                    line[4],
                    0.0,
                    0.0,
                ]
            )
            # Sumamos los importes a los totalizadores:
            footer[7] += line[3]
            footer[8] += line[4]

        # Nos queda el ultimo footer sin appendear ya que no hay iteración
        moves.append(footer)

        return self.env.ref(
            'l10n_ar_eynes.action_report_libro_diario'
        ).report_action(
            self,
            data={
                'options': [],
                'move_headers': move_headers,
                'moves': moves,
                'company': self.company_id.id,
            },
        )


class LibroDiarioQWEBReport(models.AbstractModel):
    _name = 'report.l10n_ar_eynes.libro_diario_qweb'
    _description = 'LibroDiarioQWEBReport'

    @api.model
    def _get_report_values(self, docids, data=None):
        data.update(
            {'company': self.env['res.company'].browse(data['company'])}
        )

        model = self.env.context.get('active_model')
        docs = self.env[model].browse(self.env.context.get('active_id'))

        return {
            'doc_ids': self.ids,
            'doc_model': model,
            'data': data,
            'docs': docs,
        }
