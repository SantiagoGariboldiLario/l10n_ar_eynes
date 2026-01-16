/** @odoo-module */

import {PaymentScreenStatus} from "@point_of_sale/app/screens/payment_screen/payment_status/payment_status";
import {patch} from "@web/core/utils/patch";

patch(PaymentScreenStatus.prototype, {
    getTaxesTotals(taxNameContains) {
        let total = 0.0;
        const groupTaxes = {};

        this.props.order.orderlines.forEach(function (line) {
            const taxDetails = line.get_tax_details();
            const taxIds = Object.keys(taxDetails);

            for (let t = 0; t < taxIds.length; t++) {
                const taxId = taxIds[t];
                if (!(taxId in groupTaxes)) {
                    groupTaxes[taxId] = 0;
                }

                const taxAmount = parseFloat(taxDetails[taxId].amount);
                if (!isNaN(taxAmount)) {
                    groupTaxes[taxId] += taxAmount;
                } else {
                    console.error(`Tax amount for tax ID ${taxId} is not a valid number`, taxDetails[taxId]);
                }
            }
        });

        const taxIds = Object.keys(groupTaxes);

        for (let j = 0; j < taxIds.length; j++) {
            const taxAmount = groupTaxes[taxIds[j]];
            const taxName = this.env.services.pos.taxes_by_id[taxIds[j]].name;

            if (taxName.toLowerCase().startsWith(taxNameContains)) {
                total += taxAmount;
            }
        }
        return total;
    },

    get total_iva_and_retentions() {
        const total_value = this.getTaxesTotals("iva");
        return this.env.utils.formatCurrency(total_value);
    },

    get total_perceptions() {
        return this.env.utils.formatCurrency(this.props.order.get_total_perception());
    },
});
