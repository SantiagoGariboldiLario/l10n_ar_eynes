from datetime import datetime
from dateutil.relativedelta import relativedelta as relatived

from odoo import api, fields, models
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT as DSDF


class IVADDJJ(models.TransientModel):
    _name = "iva.ddjj"
    _description = "IVA DDJJ Report"

    company_id = fields.Many2one('res.company', string="Company", required=True)
    config_id = fields.Many2one(
        'iva.ddjj.config', string="Configuration", required=True
    )
    period = fields.Date(string="Period", required=True, default=lambda self: fields.Date.today().replace(day=1))

    def _get_period_domain(self):
        dt = datetime.strptime(str(self.period), DSDF)
        date_start = (dt + relatived(day=1)).strftime(DSDF)
        date_finish = (dt + relatived(day=31)).strftime(DSDF)
        return date_start, date_finish

    def _get_invoice_vat_moves(self, report_type):
        move_type = ('out_invoice', 'out_refund') if report_type == 'sale' else ('in_invoice', 'in_refund')
        sign = -1 if report_type == 'sale' else 1
        date_from, date_to = self._get_period_domain()
        query = """
            SELECT
                sum(aml.balance * %(sign)s) AS total
            FROM account_move_line aml
            LEFT JOIN account_move am ON aml.move_id = am.id
            LEFT JOIN account_tax at ON aml.tax_line_id = at.id
            LEFT JOIN account_tax_group atg ON at.tax_group_id = atg.id
            WHERE
                atg.group_type = 'vat'
                AND
        """
        query += 'am.invoice_date' if report_type == 'sale' else 'am.date'
        query += """ BETWEEN %(date_from)s AND %(date_to)s
                AND am.move_type IN %(inv_type)s
                AND am.company_id = %(company_id)s
                AND am.state = 'posted'
        """
        q_vals = {
            'sign': sign,
            'date_from': date_from,
            'date_to': date_to,
            'inv_type': tuple(move_type),
            'company_id': self.company_id.id,
        }
        self._cr.execute(query, q_vals)
        res = self._cr.dictfetchone()
        return res.get('total', 0.0) if res else 0.0

    def _get_overpayment_moves(self):
        date_from, _date_to = self._get_period_domain()
        # Return the latest positive balance per configured account (max date <= date_from)
        # and then order the returned records by date DESC (most recent first).
        query = """
            SELECT t.account_id, t.amount, t.date
            FROM (
                SELECT DISTINCT ON (aml.account_id)
                    aml.account_id,
                    aml.balance AS amount,
                    aml.date
                FROM iva_ddjj_config ic
                INNER JOIN account_move_line aml ON aml.account_id IN (
                    ic.free_availability_balance_account_id,
                    ic.last_period_balance_account_id
                )
                LEFT join account_move am ON aml.move_id = am.id
                WHERE
                    ic.id = %(config_id)s
                    AND aml.date <= %(date_from)s
                    AND aml.company_id = %(company_id)s
                    AND aml.balance > 0
                    AND am.state = 'posted'
                ORDER BY aml.account_id, aml.date DESC
            ) t
            ORDER BY t.date DESC

        """
        q_vals = {
            'config_id': self.config_id.id,
            'date_from': date_from,
            'company_id': self.company_id.id,
        }
        self._cr.execute(query, q_vals)
        all_res = self._cr.dictfetchall()

        previous_free_availability_balance = 0.0
        previous_balance = 0.0
        last_date = None
        for res in all_res:
            res_date = res['date']
            if not last_date:
                last_date = res_date
            if res_date == last_date:
                if res['account_id'] == self.config_id.free_availability_balance_account_id.id:
                    previous_free_availability_balance = res['amount']
                elif res['account_id'] == self.config_id.last_period_balance_account_id.id:
                    previous_balance = res['amount']
            else:
                break

        return previous_balance, previous_free_availability_balance

    def _get_retention_data(self):
        query = """
        SELECT sum(r.amount) AS amount FROM account_payment_order_retention_line r
        JOIN account_tax at ON r.retention_id = at.id
        WHERE r.date BETWEEN %(date_start)s AND %(date_end)s
        AND at.type_tax_use LIKE 'sale'
        AND at.retention_type LIKE 'vat'
        AND r.company_id = %(company)s
        GROUP BY at.id
        """
        date_from, date_to = self._get_period_domain()
        q_vals = {
            'date_start': date_from,
            'date_end': date_to,
            'company': self.company_id.id,
        }
        self._cr.execute(query, q_vals)
        res = self._cr.dictfetchone()
        return res.get('amount', 0.0) if res else 0.0

    def _get_perception_data(self):
        query = """
        SELECT sum(p.amount) AS amount FROM perception_tax_line p
        JOIN account_tax at ON p.perception_id = at.id
        JOIN account_move i ON p.invoice_id = i.id
        WHERE p.date BETWEEN %(date_start)s AND %(date_end)s
        AND i.state = 'posted'
        AND at.type_tax_use LIKE 'purchase'
        AND at.retention_type LIKE 'vat'
        AND p.company_id = %(company)s
        GROUP BY at.id
        """
        date_from, date_to = self._get_period_domain()
        q_vals = {
            'date_start': date_from,
            'date_end': date_to,
            'company': self.company_id.id,
        }
        self._cr.execute(query, q_vals)
        res = self._cr.dictfetchone()
        return res.get('amount', 0.0) if res else 0.0

    def _get_vat_info(self):
        sales_amount = self._get_invoice_vat_moves('sale')
        purchase_amount = self._get_invoice_vat_moves('purchase')
        previous_balance, previous_free_availability_balance = self._get_overpayment_moves()
        retention_amount = self._get_retention_data()
        perception_amount = self._get_perception_data()

        technical_balance = sales_amount - purchase_amount - previous_balance
        technical_balance_partner = abs(technical_balance) if technical_balance < 0 else 0.0
        technical_balance_arca = abs(technical_balance) if technical_balance > 0 else 0.0

        free_availability_balance = - previous_free_availability_balance - retention_amount - perception_amount
        result = technical_balance + free_availability_balance
        result_arca = result if result > 0 else 0.0

        return [
            ['IVA Débito Fiscal', sales_amount],
            ['IVA Crédito Fiscal', -1 * purchase_amount],
            ['IVA Saldo a Favor del Período Anterior', -1 * previous_balance],
            ['IVA Saldo Técnico a Favor del Contribuyente', technical_balance_partner],
            ['IVA Saldo Técnico a Favor del ARCA', technical_balance_arca],
            ['Retenciones IVA', -1 * retention_amount],
            ['Percepciones IVA', -1 * perception_amount],
            ['IVA Saldo a Favor de Libre Disponibilidad del Período Anterior', -1 * previous_free_availability_balance],
            ['IVA Saldo a Favor de Libre Disponibilidad del Período', free_availability_balance],
            ['IVA Saldo del Impuesto a Favor del ARCA', result_arca],
        ]

    def create_pdf(self):
        self.ensure_one()
        vat_info = self._get_vat_info()
        date_start, date_end = self._get_period_domain()
        return self.env.ref(
            'l10n_ar_taxes_report.action_report_iva_ddjj'
        ).report_action(
            self,
            data={
                'options': [],
                'vat_info': vat_info,
                'date_start': date_start,
                'date_end': date_end,
            },
        )


class IVADDJJQWEBReport(models.AbstractModel):
    _name = 'report.l10n_ar_taxes_report.iva_ddjj_qweb'
    _description = 'IVADDJJQWEBReport'

    @api.model
    def _get_report_values(self, docids, data=None):
        model = self.env.context.get('active_model')
        docs = self.env[model].browse(self.env.context.get('active_id'))

        return {
            'doc_ids': self.ids,
            'doc_model': model,
            'data': data,
            'docs': docs,
        }
