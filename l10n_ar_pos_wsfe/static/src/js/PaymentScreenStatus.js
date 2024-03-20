odoo.define('l10n_ar_pos_wsfe.WSFEPaymentScreenStatus', function(require) {
    'use strict';

    var PaymentScreenStatus = require("point_of_sale.PaymentScreenStatus");
    const Registries = require("point_of_sale.Registries");
    var utils = require('web.utils');
    var round_pr = utils.round_precision;

    const WSFEPaymentScreenStatus = (PaymentScreenStatus) =>
        class extends PaymentScreenStatus {

            getTotal(taxNameContains) {
                let total = 0.0;
            
                let groupTaxes = {};
                this.currentOrder.orderlines.each(function (line) {
                    let taxDetails = line.get_tax_details();
                    let taxIds = Object.keys(taxDetails);
                    for (let t = 0; t<taxIds.length; t++) {
                        let taxId = taxIds[t];
                        if (!(taxId in groupTaxes)) {
                            groupTaxes[taxId] = 0;
                        }
                        groupTaxes[taxId] += taxDetails[taxId];
                    }
                });
            
                let taxIds = Object.keys(groupTaxes);
                for (let j = 0; j<taxIds.length; j++) {
                    let taxAmount = groupTaxes[taxIds[j]];
                    let taxName = this.env.pos.taxes_by_id[taxIds[j]].name;
                    
                    if(taxName.toLowerCase().includes(taxNameContains)){
                        total += taxAmount;
                    }
                }
            
                return this.env.pos.format_currency(total);
            }
            
            get total_iva() {
                return this.getTotal("iva");
            }
            
            get total_perceptions() {
                return this.getTotal("percepciones");
            }
            
        };

    Registries.Component.extend(PaymentScreenStatus, WSFEPaymentScreenStatus);

    return WSFEPaymentScreenStatus;
});