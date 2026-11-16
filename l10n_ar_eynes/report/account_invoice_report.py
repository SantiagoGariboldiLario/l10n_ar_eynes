import logging

from odoo import api, models
from odoo.tools import SQL

from odoo.addons.account.report.account_invoice_report import (
    AccountInvoiceReport as BaseAccountInvoiceReport,
)

_logger = logging.getLogger(__name__)

PRICE_TOTAL_SQL = 'line.price_total *'
PRICE_TOTAL_FIXED_SQL = (
    '(line.price_total + COALESCE(ar_tax_adjust.adjustment, 0.0)) *'
)


class AccountInvoiceReport(models.Model):
    _inherit = 'account.invoice.report'

    # _depends no se mergea al heredar: se reconstruye desde el del core.
    _depends = {
        **BaseAccountInvoiceReport._depends,
        'account.move.line': [
            *BaseAccountInvoiceReport._depends.get('account.move.line', ()),
            'tax_ids',
            'tax_line_id',
            'display_type',
        ],
        'account.tax': ['amount', 'amount_type'],
    }

    @api.model
    def _select(self) -> SQL:
        """El price_total de la linea (core) trae los impuestos calculados
        con la alicuota fija del impuesto; los apuntes de la factura tienen el
        importe real (percepciones por padron, importes manuales). Se corrige
        el Total con la diferencia calculada en ar_tax_adjust (ver _from)."""
        select = super()._select()
        if select.params or PRICE_TOTAL_SQL not in select.code:
            _logger.warning(
                'account.invoice.report: no se pudo ajustar price_total '
                'con el importe real de los impuestos.'
            )
            return select
        return SQL(select.code.replace(PRICE_TOTAL_SQL, PRICE_TOTAL_FIXED_SQL))

    @api.model
    def _from(self) -> SQL:
        # Por cada impuesto porcentual de la linea: parte proporcional (por
        # neto) del apunte de ese impuesto en la factura, menos lo que el core
        # ya sumo en price_total (neto x alicuota). Corrige percepciones e
        # impuestos internos con importe de padron / manual y el redondeo
        # global del IVA. Sin apunte para ese impuesto se deja el del core.
        return SQL(
            """%s
                LEFT JOIN LATERAL (
                    SELECT SUM(
                        perc_move.amount * line.price_subtotal
                            / NULLIF(perc_base.base, 0.0)
                        - line.price_subtotal * tax.amount / 100
                    ) AS adjustment
                    FROM account_move_line_account_tax_rel rel
                    JOIN account_tax tax
                        ON tax.id = rel.account_tax_id
                        AND tax.amount_type = 'percent'
                    CROSS JOIN LATERAL (
                        SELECT SUM(tax_line.amount_currency)
                            * (CASE WHEN move.move_type IN ('out_invoice', 'in_refund', 'out_receipt')
                                THEN -1 ELSE 1 END) AS amount
                        FROM account_move_line tax_line
                        WHERE tax_line.move_id = line.move_id
                            AND tax_line.tax_line_id = tax.id
                    ) perc_move
                    CROSS JOIN LATERAL (
                        SELECT SUM(base_line.price_subtotal) AS base
                        FROM account_move_line base_line
                        JOIN account_move_line_account_tax_rel base_rel
                            ON base_rel.account_move_line_id = base_line.id
                            AND base_rel.account_tax_id = tax.id
                        WHERE base_line.move_id = line.move_id
                            AND base_line.display_type = 'product'
                    ) perc_base
                    WHERE rel.account_move_line_id = line.id
                ) ar_tax_adjust ON TRUE
            """,
            super()._from(),
        )


class ReportInvoiceWithoutPayment(models.AbstractModel):
    _inherit = 'report.account.report_invoice'

    @api.model
    def _get_report_values(self, docids, data=None):
        rslt = super()._get_report_values(docids, data)
        docs = self.env['account.move'].browse(docids)

        qr_afip_urls = {}
        for invoice in docs:
            new_code_url = invoice.get_qr_code()
            if new_code_url:
                qr_afip_urls[invoice.id] = new_code_url

        rslt.update({'qr_code_afip': qr_afip_urls})

        return rslt
