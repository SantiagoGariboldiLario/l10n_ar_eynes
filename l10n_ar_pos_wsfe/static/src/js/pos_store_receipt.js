/** @odoo-module */

/**
 * Make sure perceptions are computed right before printing the receipt.
 * This guarantees the receipt has the latest perception amount without
 * requiring a browser refresh.
 */
import {PosStore} from "@point_of_sale/app/services/pos_store";
import {patch} from "@web/core/utils/patch";

patch(PosStore.prototype, {
    async printReceipt({basic = false, order = this.getOrder(), printBillActionTriggered = false} = {}) {
        if (order?.compute_perceptions) {
            await order.compute_perceptions();
            order.triggerRecomputeAllPrices?.();
        }
        return await super.printReceipt({basic, order, printBillActionTriggered});
    },
});
