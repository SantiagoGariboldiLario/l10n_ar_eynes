from datetime import datetime
from dateutil.relativedelta import relativedelta as relatived

from odoo import api, fields, models
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT as DSDF


class IIBBDDJJ(models.TransientModel):
    _name = "iibb.ddjj"
    _description = "IIBB DDJJ Report"

    company_id = fields.Many2one('res.company', string="Company", required=True)
    config_id = fields.Many2one(
        'iibb.ddjj.config', string="Configuration", required=True
    )
    period = fields.Date(string="Period", required=True, default=lambda self: fields.Date.today().replace(day=1))

    def _get_period_domain(self):
        dt = datetime.strptime(str(self.period), DSDF)
        date_start = (dt + relatived(day=1)).strftime(DSDF)
        date_finish = (dt + relatived(day=31)).strftime(DSDF)
        return date_start, date_finish

    def _get_invoice_moves(self, report_type):
        move_type = ('out_invoice', 'out_refund') if report_type == 'sale' else ('in_invoice', 'in_refund')
        sign = -1 if report_type == 'sale' else 1
        date_from, date_to = self._get_period_domain()
        query = """
            SELECT
                sum(aml.balance * %(sign)s) AS total,
                COALESCE(rcs2.id, rcs.id) AS Province,
                COALESCE(rcs2.name, rcs.name) AS Jurisdiccion
            FROM account_move_line aml
            LEFT JOIN account_move am ON aml.move_id = am.id
            LEFT JOIN account_account aa ON aml.account_id = aa.id
            LEFT JOIN res_partner rp ON rp.id = am.partner_id
            LEFT JOIN res_partner rp2 ON am.partner_shipping_id = rp2.id
            LEFT JOIN res_country_state rcs ON rcs.id = rp.state_id
            LEFT JOIN res_country_state rcs2 ON rcs2.id = rp2.state_id
            WHERE
                aa.account_type NOT LIKE '%%payable'
                AND aa.account_type NOT LIKE '%%receivable'
                AND
        """
        query += 'am.invoice_date'  if report_type == 'sale' else 'am.date'
        query += """ BETWEEN %(date_from)s AND %(date_to)s
                AND am.move_type IN %(inv_type)s
                AND am.company_id = %(company_id)s
                AND am.state = 'posted'
                AND aml.tax_line_id IS NULL
            GROUP BY Province, Jurisdiccion
        """
        q_vals = {
            'sign': sign,
            'date_from': date_from,
            'date_to': date_to,
            'inv_type': tuple(move_type),
            'company_id': self.company_id.id,
        }
        self._cr.execute(query, q_vals)
        res = self._cr.dictfetchall()
        return res

    def _get_overpayment_moves(self):
        date_from, _date_to = self._get_period_domain()
        query = """
            SELECT
                icl.state_id,
                icl.account_id,
                aml.balance AS amount,
                aml.date,
                rcs.name
            FROM iibb_ddjj_config_jurisdiction_line icl
            INNER JOIN account_move_line aml ON icl.account_id = aml.account_id
            LEFT JOIN res_country_state rcs ON rcs.id = icl.state_id
            WHERE
                icl.config_id = %(config_id)s
                AND aml.date <= %(date_from)s
                AND aml.company_id = %(company_id)s
                AND aml.balance > 0
            ORDER BY date desc
        """
        q_vals = {
            'config_id': self.config_id.id,
            'date_from': date_from,
            'company_id': self.company_id.id,
        }
        self._cr.execute(query, q_vals)
        res = self._cr.dictfetchall()
        return res

    def _get_retention_data(self):
        query = """
        SELECT at.state_id AS province, rcs.name AS jurisdiccion, sum(r.amount) AS amount FROM account_payment_order_retention_line r
        JOIN account_tax at ON r.retention_id = at.id
        JOIN res_country_state rcs ON rcs.id = at.state_id
        WHERE r.date BETWEEN %(date_start)s AND %(date_end)s
        AND at.type_tax_use LIKE 'sale'
        AND r.company_id = %(company)s
        GROUP BY at.id, rcs.name
        """
        date_from, date_to = self._get_period_domain()
        q_vals = {
            'date_start': date_from,
            'date_end': date_to,
            'company': self.company_id.id,
        }
        self._cr.execute(query, q_vals)
        retention_res = self._cr.dictfetchall()
        return retention_res

    def _get_perception_data(self):
        query = """
        SELECT at.state_id AS province, rcs.name AS jurisdiccion, sum(p.amount) AS amount FROM perception_tax_line p
        JOIN account_tax at ON p.perception_id = at.id
        JOIN res_country_state rcs ON rcs.id = at.state_id
        JOIN account_move i ON p.invoice_id = i.id
        WHERE p.date BETWEEN %(date_start)s AND %(date_end)s
        AND i.state = 'posted'
        AND at.type_tax_use LIKE 'purchase'
        AND p.company_id = %(company)s
        GROUP BY at.id, rcs.name
        """
        date_from, date_to = self._get_period_domain()
        q_vals = {
            'date_start': date_from,
            'date_end': date_to,
            'company': self.company_id.id,
        }
        self._cr.execute(query, q_vals)
        perception_res = self._cr.dictfetchall()
        return perception_res

    def _get_state_info(self):
        sales_amount = self._get_invoice_moves('sale')
        overpayment_amount = self._get_overpayment_moves()
        retention_amount = self._get_retention_data()
        perception_amount = self._get_perception_data()
        state_info = {}
        for sale in sales_amount:
            state_id = sale['province']
            state_identifier = (state_id, sale['jurisdiccion'])
            state_info.setdefault(state_identifier, {'debts': 0.0})
            base = sale['total']
            config_state_line = self.config_id.jurisdiction_line_ids.filtered(
                lambda line:
                    line.state_id.id == state_id
            )
            percentage = 0.0
            if config_state_line:
                percentage = config_state_line.percentage
            state_info[state_identifier]['sale_total'] = base
            state_info[state_identifier]['tax_amount'] = round(base * percentage, 2)
        for overpayment in overpayment_amount:
            state_identifier = (overpayment['state_id'], overpayment['name'])
            state_info.setdefault(state_identifier, {'debts': 0.0})
            if not (state_info[state_identifier].get('overpayment_total', 0.0) > 0.0):
                state_info[state_identifier]['overpayment_total'] = overpayment['amount']
        for perc_ret in retention_amount + perception_amount:
            state_id = perc_ret['province']
            state_identifier = (state_id, perc_ret['jurisdiccion'])
            state_info.setdefault(state_identifier, {'debts': 0.0})
            state_info[state_identifier]['debts'] += perc_ret['amount']
        return state_info

    def _convert_to_list(self, state_info):
        state_info_list = []
        for key, value in state_info.items():
            tax_amount = value.get('tax_amount', 0.0)
            debts = value.get('overpayment_total', 0.0) + value.get('debts', 0.0)
            result = tax_amount - debts
            state_result = [
                key[1],
                tax_amount,
                debts,
                0.0,
                abs(result) if result < 0 else 0.0,
                result if result > 0 else 0.0,
            ]
            state_info_list.append(state_result)
        return state_info_list

    def create_pdf(self):
        self.ensure_one()
        state_info = self._get_state_info()
        state_info = self._convert_to_list(state_info)
        date_start, date_end = self._get_period_domain()
        return self.env.ref(
            'l10n_ar_taxes_report.action_report_iibb_ddjj'
        ).report_action(
            self,
            data={
                'options': [],
                'state_info': state_info,
                'date_start': date_start,
                'date_end': date_end,
            },
        )


class IIBBDDJJQWEBReport(models.AbstractModel):
    _name = 'report.l10n_ar_taxes_report.iibb_ddjj_qweb'
    _description = 'IIBBDDJJQWEBReport'

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
