import json
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class SaleVATWizard(models.TransientModel):
    _name = 'sale.vat.wizard'
    _description = 'Sale VAT Wizard'

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

    def _get_sale_data(self):
        query = """
        SELECT
            afp.id as fiscal_position_id,
            aml.move_id,
            aml.id,
            aml.fiscal_credit,
            aml.price_subtotal,
            aml.price_total,
            amlat.account_tax_id as applied_tax_id,
            am.currency_rate,
            am.move_type
        FROM account_move_line aml
        JOIN account_move am ON aml.move_id = am.id
        JOIN account_fiscal_position afp ON am.fiscal_position_id = afp.id
        LEFT JOIN account_move_line_account_tax_rel amlat ON aml.id = amlat.account_move_line_id
        WHERE
            am.state = 'posted' AND
            am.move_type in ('out_invoice', 'out_refund') AND
            am.date >= %(date_start)s AND
            am.date <= %(date_end)s AND
            am.company_id = %(company)s AND
            aml.display_type = 'product'
        ORDER BY
            afp.id, aml.move_id, aml.id
        """
        vals = {
            'date_start': self.date_start,
            'date_end': self.date_end,
            'company': self.company_id.id,
        }
        self.env.cr.execute(query, vals)
        res = self.env.cr.fetchall()
        return res

    def _parse_tax_debit_refunds(self):
        sale_data = self._get_sale_data()
        by_fiscal_credit = {
            'direct_taxed': {
                '10.5': [0.0, 0.0],
                '21': [0.0, 0.0],
                '27': [0.0, 0.0],
            },
            'apport': {
                '10.5': [0.0, 0.0],
                '21': [0.0, 0.0],
                '27': [0.0, 0.0],
            },
            'direct_exempt': {
                '10.5': [0.0, 0.0],
                '21': [0.0, 0.0],
                '27': [0.0, 0.0],
            },
            'direct_taxed_refund': {
                '10.5': [0.0, 0.0],
                '21': [0.0, 0.0],
                '27': [0.0, 0.0],
            },
            'apport_refund': {
                '10.5': [0.0, 0.0],
                '21': [0.0, 0.0],
                '27': [0.0, 0.0],
            },
            'direct_exempt_refund': {
                '10.5': [0.0, 0.0],
                '21': [0.0, 0.0],
                '27': [0.0, 0.0],
            },
            'exempt': 0.0,
            'untaxed': 0.0,
            'ni_nr_ex_mon': 0.0,
            'exempt_refund': 0.0,
            'untaxed_refund': 0.0,
            'ni_nr_ex_mon_refund': 0.0,
        }

        vat_type = None
        for i, line in enumerate(sale_data):
            next_line = sale_data[i + 1] if i + 1 < len(sale_data) else None
            next_is_same_aml = next_line[1] == line[1] if next_line else False

            if line[0] == self.env.ref('l10n_ar_eynes.fiscal_position_ri').id:
                if (
                    line[6]
                    == self.env.ref('l10n_ar_eynes.10_50_percent_tax_sale').id
                ):
                    vat_type = '10.5'
                elif (
                    line[6]
                    == self.env.ref('l10n_ar_eynes.21_percent_tax_sale').id
                ):
                    vat_type = '21'
                elif (
                    line[6]
                    == self.env.ref('l10n_ar_eynes.27_percent_tax_sale').id
                ):
                    vat_type = '27'
                elif (
                    line[6]
                    == self.env.ref('l10n_ar_eynes.exempt_percent_tax_sale').id
                ):
                    vat_type = 'exempt'
            else:
                vat_type = 'ni_nr_ex_mon'

            if not next_is_same_aml:
                total = line[5] * line[7]
                if not vat_type:
                    vat_type = 'untaxed'

                if vat_type in ['exempt', 'ni_nr_ex_mon', 'untaxed']:
                    if line[8] == 'out_refund':
                        vat_type = vat_type + '_refund'
                        total = total * -1
                    by_fiscal_credit[vat_type] += total
                else:
                    fiscal_credit = line[3]
                    net = line[4] * line[7]
                    vat = total - net
                    if line[8] == 'out_refund':
                        fiscal_credit = fiscal_credit + '_refund'
                        net = net * -1
                        vat = vat * -1
                    by_fiscal_credit[fiscal_credit][vat_type][0] += net
                    by_fiscal_credit[fiscal_credit][vat_type][1] += vat
                vat_type = None

        for fiscal_type in (
            'direct_taxed',
            'apport',
            'direct_exempt',
            'direct_taxed_refund',
            'apport_refund',
            'direct_exempt_refund',
        ):
            aliquots = (
                by_fiscal_credit[fiscal_type]['10.5'],
                by_fiscal_credit[fiscal_type]['21'],
                by_fiscal_credit[fiscal_type]['27'],
            )
            by_fiscal_credit[fiscal_type] = aliquots

        return by_fiscal_credit

    def _get_retention_data(self):
        retention_query = """
        SELECT ret.name, -1 * sum(r.amount) FROM account_payment_order_retention_line r
        JOIN account_tax ret ON r.retention_id = ret.id
        WHERE r.date BETWEEN %(date_start)s AND %(date_end)s
        AND ret.type_tax_use LIKE 'purchase'
        AND r.company_id = %(company)s
        GROUP BY ret.id
        """
        vals = {
            'date_start': self.date_start,
            'date_end': self.date_end,
            'company': self.company_id.id,
        }
        self.env.cr.execute(retention_query, vals)
        retention_res = self.env.cr.fetchall()
        return retention_res

    def _get_perception_data(self):
        perception_query = """
        SELECT per.name, sum(p.amount) FROM perception_tax_line p
        JOIN account_tax per ON p.perception_id = per.id
        JOIN account_move i ON p.invoice_id=i.id
        WHERE p.date BETWEEN %(date_start)s AND %(date_end)s
        AND i.state = 'posted'
        AND per.type_tax_use LIKE 'sale'
        AND p.company_id = %(company)s
        GROUP BY per.id
        """
        vals = {
            'date_start': self.date_start,
            'date_end': self.date_end,
            'company': self.company_id.id,
        }
        self.env.cr.execute(perception_query, vals)
        perception_res = self.env.cr.fetchall()
        return perception_res

    def _parse_retention_perception(self):
        taxes_data = self._get_retention_data() + self._get_perception_data()
        taxes_data_parsed = []
        for line in taxes_data:
            taxes_data_parsed.append(
                (line[0].get('es_AR', line[0].get('en_US', 'No name')), line[1])
            )
        return taxes_data_parsed

    def run(self):
        tax_debit_refunds = self._parse_tax_debit_refunds()
        retention_perception = self._parse_retention_perception()

        return self.env.ref(
            'l10n_ar_eynes.action_report_sale_vat'
        ).report_action(
            self,
            data={
                'options': [],
                'direct_taxed': tax_debit_refunds['direct_taxed'],
                'apport': tax_debit_refunds['apport'],
                'direct_exempt': tax_debit_refunds['direct_exempt'],
                'direct_taxed_refund': tax_debit_refunds['direct_taxed_refund'],
                'apport_refund': tax_debit_refunds['apport_refund'],
                'direct_exempt_refund': tax_debit_refunds[
                    'direct_exempt_refund'
                ],
                'exempt': tax_debit_refunds['exempt'],
                'untaxed': tax_debit_refunds['untaxed'],
                'ni_nr_ex_mon': tax_debit_refunds['ni_nr_ex_mon'],
                'exempt_refund': tax_debit_refunds['exempt_refund'],
                'untaxed_refund': tax_debit_refunds['untaxed_refund'],
                'ni_nr_ex_mon_refund': tax_debit_refunds['ni_nr_ex_mon_refund'],
                'retention_perception': retention_perception,
                'cero': 0.0,
                'fees': 0.0,
                'internal_taxes': 0.0,
                'cero_refund': 0.0,
                'fees_refund': 0.0,
                'internal_taxes_refund': 0.0,
            },
        )


class SaleVATQWEBReport(models.AbstractModel):
    _name = 'report.l10n_ar_eynes.sale_vat_qweb'
    _description = 'SaleVATQWEBReport'

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
