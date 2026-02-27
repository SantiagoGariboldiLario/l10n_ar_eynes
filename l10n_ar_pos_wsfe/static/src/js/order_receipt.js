/** @odoo-module */

import {OrderReceipt} from "@point_of_sale/app/screens/receipt_screen/receipt/order_receipt";
import {patch} from "@web/core/utils/patch";

patch(OrderReceipt.prototype, {
    setup() {
        super.setup(...arguments);
        // Ensure perceptions are computed once before the first render of the receipt.
        if (!this.order._perception_synced_for_receipt && this.order?.compute_perceptions) {
            this.order._perception_synced_for_receipt = true;
            Promise.resolve(this.order.compute_perceptions())
                .then(() => {
                    this.order.triggerRecomputeAllPrices?.();
                    // Force a refresh so the perception line shows without needing a page reload.
                    this.render?.();
                })
                .catch((error) => {
                    void error;
                });
        }
    },

    get totalWithPerception() {
        return (
            (this.order.priceExcl || 0) +
            (this.order.amountTaxes || 0) +
            (this.order.get_total_perception?.() || 0)
        );
    },
});
