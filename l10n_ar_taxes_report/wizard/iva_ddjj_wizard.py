from datetime import datetime
from dateutil.relativedelta import relativedelta as relatived

from odoo import fields, models
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
        query += 'am.invoice_date' if report_type == 'sale' else 'am.date'
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

    def create_pdf(self):
        self.ensure_one()
        # return self.env.ref('l10n_ar_taxes_report.action_report_iva_ddjj').report_action(self)
        return True
