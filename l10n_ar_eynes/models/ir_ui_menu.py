# Part of Odoo. See LICENSE file for full copyright and licensing details.


from odoo import models


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    def _load_menus_blacklist(self):
        """
        Se ocultan los menú 'purchase_vat_exporter_menu' y 'sale_vat_exporter_menu' para Compañias que no
        estén configuradas para operar con IVA prorrateable (apportionable_vat = True)
        """
        res = super()._load_menus_blacklist()
        if not self.env.company.apportionable_vat:
            res += [
                self.env.ref('l10n_ar_eynes.purchase_vat_exporter_menu').id,
                self.env.ref('l10n_ar_eynes.sale_vat_exporter_menu').id,
            ]
        return res
