odoo.define("l10n_ar_pos_wsfe.ProductScreen", function (require) {
    "use strict";

    // eslint-disable-next-line no-shadow
    const ProductScreen = require("point_of_sale.ProductScreen");
    const Registries = require("point_of_sale.Registries");

    const PosWSFEProductScreen = (ProductScreen) =>
        class extends ProductScreen {
            // eslint-disable-next-line no-unused-vars
            async _updateSelectedOrderline(event) {
                const res = super._updateSelectedOrderline(...arguments);
                await this.env.pos.get_order().compute_perceptions();
                return res;
            }
        };

    Registries.Component.extend(ProductScreen, PosWSFEProductScreen);

    return ProductScreen;
});
