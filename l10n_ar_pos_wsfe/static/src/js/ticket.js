odoo.define("l10n_ar_pos_wsfe.WSFETicketScreen", function (require) {
    "use strict";

    // eslint-disable-next-line no-shadow
    const TicketScreen = require("point_of_sale.TicketScreen");
    const Registries = require("point_of_sale.Registries");

    const WSFETicketScreen = (TicketScreen) =>
        class extends TicketScreen {
            getDocOrigin(order) {
                return order.doc_origin || "";
            }
            async _onDoRefund() {
                await super._onDoRefund(...arguments);
                await this.props.destinationOrder.compute_perceptions();
            }
        };

    Registries.Component.extend(TicketScreen, WSFETicketScreen);

    return WSFETicketScreen;
});
