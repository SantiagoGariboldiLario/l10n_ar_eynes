##############################################################################
#
#   Copyright (c) 2022-2023 Eynes SRL  (Eynes - Ingenieria del software)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
#
##############################################################################

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class COTNomenclature(models.Model):
    _name = "cot.nomenclature"
    _rec_name = "code"

    name = fields.Char(string="Name")
    code = fields.Char(string="Code", size=6)


class UoM(models.Model):
    _inherit = "uom.uom"

    cot_code = fields.Char(string="COT Code")


class ProductTemplate(models.Model):
    _inherit = "product.template"

    area_id = fields.Many2one('product.area')
    cot_nomenclature_id = fields.Many2one(
        "cot.nomenclature",
        string="COT Nomenclature",
    )
    fiscal_credit = fields.Selection(
        [
            ('direct_taxed', 'Direct Taxed'),
            ('direct_exempt', 'Direct Exempt'),
            ('apport', 'Apport'),
        ]
    )
    manufacturer_id = fields.Many2one('res.company')
    show_fiscal_credit = fields.Boolean(
        default=lambda self: self.env["ir.config_parameter"]
        .sudo()
        .get_param("l10n_ar_eynes.apportionable_vat"),
        store=False,
    )

    @api.onchange("cot_nomenclature_id")
    def onchange_cot_nomenclature_id(self):
        product_products = self.env["product.product"].search(
            [("default_code", "=", self.default_code)]
        )

        for product in product_products:
            product.write({"cot_nomenclature_id": self.cot_nomenclature_id.id})


class ProductProduct(models.Model):
    _inherit = "product.product"

    cot_nomenclature_id = fields.Many2one(
        "cot.nomenclature",
        string="COT Nomenclature",
    )

    @api.onchange("cot_nomenclature_id")
    def onchange_cot_nomenclature_id(self):
        product_templates = self.env["product.template"].search(
            [("default_code", "=", self.default_code)]
        )

        for product in product_templates:
            product.write({"cot_nomenclature_id": self.cot_nomenclature_id.id})
