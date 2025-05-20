##############################################################################
#   Copyright (c) 2025 Eynes/E-MIPS (www.eynes.com.ar)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
##############################################################################

import logging


from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class InternalTaxLine(models.Model):
    _name = "internal.tax.line"
    _description = "Internal Tax Line"

    name = fields.Char(
        string='Tax',
        required=True,
        size=64,
        compute='_compute_name',
        store=True,
        copy=True,
    )
    invoice_id = fields.Many2one(
        'account.move', string='Invoice', ondelete='cascade'
    )
    base = fields.Float(digits='Account', required=True)
    amount = fields.Float(digits='Account', required=True)
    tax_id_domain = fields.Binary(compute='_compute_tax_id_domain')
    tax_id = fields.Many2one(
        'account.tax',
        string='Perception Tax',
        required=True,
        help="Perception configuration used for this perception tax, "
        "where all the configuration resides. Accounts, Tax Codes, etc.",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self._default_company_id(),
        readonly=True,
        required=True,
        store=True,
    )
    manual = fields.Boolean(default=True)

    def _default_company_id(self):
        return self.env.company.id

    @api.depends('tax_id')
    def _compute_name(self):
        for rec in self:
            rec.name = '' if not rec.tax_id else rec.tax_id.name

    @api.depends('invoice_id')
    def _compute_tax_id_domain(self):
        for rec in self:
            domain = [
                ('tax_group_id.group_type', '=', 'internals'),
                ('company_id', '=', rec.env.company.id),
            ]
            if rec.invoice_id:
                if rec.invoice_id.is_purchase_document():
                    domain.append(('type_tax_use', '=', 'purchase'))
                elif rec.invoice_id.is_sale_document():
                    domain.append(('type_tax_use', '=', 'sale'))
            rec.tax_id_domain = domain
