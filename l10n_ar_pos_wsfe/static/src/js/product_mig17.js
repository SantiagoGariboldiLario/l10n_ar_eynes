/** @odoo-module */

import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import {patch} from "@web/core/utils/patch";

patch(ProductScreen.prototype, {
    setup() {
        super.setup();

        this.numberBuffer.use({
            triggerAtInput: (...args) => {
                if (!this.pos.tempScreenIsShown) {
                    this.updateSelectedOrderline(...args);
                }
                this.currentOrder.compute_perceptions();
            },
            useWithBarcode: true,
        });
    },
    async _updateSelectedOrderline(event) {
        const res = super._updateSelectedOrderline(...arguments);
        await this.env.pos.get_order().compute_perceptions();
        return res;
    }
});
