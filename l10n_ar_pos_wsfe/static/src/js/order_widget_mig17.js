/** @odoo-module */

import {OrderWidget} from "@point_of_sale/app/generic_components/order_widget/order_widget";
import {patch} from "@web/core/utils/patch";

patch(OrderWidget.prototype, {
    _onNewOrder(order) {
        const res = super._onNewOrder(...arguments);
        if (order) {
            order.on("order-summary", this._updateSummary, this);
        }
        return res;
    },

    _onPrevOrder(order) {
        const res = super._onPrevOrder(...arguments);
        if (order) {
            order.off("order-summary", null, this);
        }
        return res;
    },

    _updateSummary() {
        const perception = this.order ? this.order.get_total_perception() : 0;
        this.state.perception = this.env.pos.format_currency(perception);
        this.state.show_perception = perception != 0;
        return super._updateSummary();
    },
});
