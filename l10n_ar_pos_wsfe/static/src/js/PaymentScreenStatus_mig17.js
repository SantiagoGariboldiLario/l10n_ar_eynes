/** @odoo-module */

import {PaymentScreenStatus} from "@point_of_sale/app/screens/payment_screen/payment_status/payment_status";
import {patch} from "@web/core/utils/patch";

patch(PaymentScreenStatus.prototype, {
    getTaxesTotals(taxNameContains) {
        let total = 0.0;
        let groupTaxes = {};

        this.props.order.orderlines.forEach(function (line) {
            let taxDetails = line.get_tax_details();
            let taxIds = Object.keys(taxDetails);

            for (let t = 0; t < taxIds.length; t++) {
                let taxId = taxIds[t];
                if (!(taxId in groupTaxes)) {
                    groupTaxes[taxId] = 0;
                }
                groupTaxes[taxId] += taxDetails[taxId];
            }
        });

        let taxIds = Object.keys(groupTaxes);
        for (let j = 0; j < taxIds.length; j++) {
            let taxAmount = groupTaxes[taxIds[j]];
            let taxName = this.env.services.pos.taxes_by_id[taxIds[j]].name;

            if (taxName.toLowerCase().startsWith(taxNameContains)) {
                total += taxAmount;
            }
        }
        return total;
    },

    get total_iva_and_retentions() {
        let total_value = this.getTaxesTotals("iva") + this.getTaxesTotals("retenciones");
        return this.env.utils.isValidFloat(total_value);
    },

    get total_perceptions() {
        return this.env.utils.formatCurrency(this.props.order.perception_amount);
    },
});
