odoo.define("l10n_ar_pos_wsfe.OrderWidget", function (require) {
    "use strict";

    // eslint-disable-next-line no-shadow
    const OrderWidget = require("point_of_sale.OrderWidget");
    const Registries = require("point_of_sale.Registries");

    const PosWSFEOrderWidget = (OrderWidget) =>
        class extends OrderWidget {
            _onNewOrder(order) {
                const res = super._onNewOrder(...arguments);
                if (order) {
                    order.on("change-summary", this._updateSummary, this);
                }
                return res;
            }
            _onPrevOrder(order) {
                const res = super._onPrevOrder(...arguments);
                if (order) {
                    order.off("change-summary", null, this);
                }
                return res;
            }

            _updateSummary() {
                const perception = this.order ? this.order.get_total_perception() : 0;
                this.state.perception = this.env.pos.format_currency(perception);
                this.state.show_perception = perception != 0;
                return super._updateSummary();
            }
        };

    Registries.Component.extend(OrderWidget, PosWSFEOrderWidget);

    return OrderWidget;
});
