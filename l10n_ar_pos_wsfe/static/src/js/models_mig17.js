/** @odoo-module */

import {Order} from "@point_of_sale/app/store/models";
import {patch} from "@web/core/utils/patch";
import {useService} from "@web/core/utils/hooks";
import {EventBus} from "@odoo/owl";

// Backup original export_as_JSON before patching
const originalExportAsJSON = Order.prototype.export_as_JSON;

patch(Order.prototype, {
    initialize: function () {
        Order.prototype.initialize.apply(this, arguments);
        this.invoiceNumber = "";
        this.inv_manual_mode = false;
        this.inv_electronic_mode = true;
        this.to_invoice = true;
        this.invoice_journal_id = false;
        this.perception_amount = 0.0;
        this.orm = useService("orm");
        return this;
    },
    _isRefundAndSaleOrder: function () {
        if (this.orderlines.length && this.orderlines.refunded_orderline_id) return true;
        else return false;
    },
    set_invoice_number: function (seq_vals) {
        if (!seq_vals) {
            this.invoiceNumber = "";
            return;
        }
        const number = seq_vals.next_seq;
        // eslint-disable-next-line no-negated-condition
        if (!number) {
            this.invoiceNumber = "";
        } else {
            this.invoiceNumber = `[ ${seq_vals.full_sequence} ]`;
        }
    },
    set_manual_invoice: function (manual_mode) {
        this.assert_editable();
        this.set_to_invoice(manual_mode);
        if (this.is_to_invoice() === manual_mode) {
            this.inv_manual_mode = manual_mode;
        }
    },
    is_manual_invoice: function () {
        return this.inv_manual_mode;
    },
    set_electronic_invoice: function (electronic_mode) {
        this.assert_editable();
        this.set_to_invoice(electronic_mode);
        if (this.is_to_invoice() === electronic_mode) {
            this.inv_electronic_mode = electronic_mode;
        }
    },
    is_electronic_invoice: function () {
        return this.inv_electronic_mode;
    },
    set_invoice_journal: function (journal_id) {
        this.invoice_journal_id = journal_id;
    },
    export_as_JSON: function () {
        // Call the original method to avoid recursion
        var json = originalExportAsJSON.apply(this, arguments);

        // Add custom properties to the JSON
        json.inv_manual_mode = this.inv_manual_mode ? this.inv_manual_mode : false;
        json.inv_electronic_mode = this.inv_electronic_mode ? this.inv_electronic_mode : false;
        json.invoice_journal_id = this.invoice_journal_id || false;
        json.doc_origin = this.doc_origin || "";

        return json;
    },
    // eslint-disable-next-line no-unused-vars
    init_from_JSON(json) {
        this._on_init_json = true;
        super.init_from_JSON(...arguments);
        this._on_init_json = false;
        this.inv_manual_mode = false;
        this.inv_electronic_mode = true;
        this.to_invoice = true;
        this.invoice_journal_id = false;
        this.doc_origin = json.doc_origin || "";
        this.compute_perceptions();
    },

    /* -- Percepcions -- */
    _prepare_lines_to_compute_perception() {
        return this.get_orderlines().map((line) => ({
            product_id: line.product.id,
            qty: line.quantity,
            price: line.price,
            tax_ids: line.tax_ids || line.product.taxes_id || [],
            discount: line.discount,
            price_subtotal: line.get_price_without_tax(),
            price_total: line.get_price_with_tax(),
        }));
    },
    _prepare_order_vals: function () {
        const partner = this.get_partner();
        let date = false;
        if (this.creation_date) {
            date = this.creation_date.toISOString().slice(0, 10);
        }
        return {
            partner_id: partner ? partner.id : false,
            date: date || false,
            untaxed_amount: this.get_total_without_tax(),
            tax_amount: this.get_total_tax(),
            invoice_type: this._isRefundAndSaleOrder() ? "out_refund" : "out_invoice",
            order_lines: this._prepare_lines_to_compute_perception(),
            currency_id: this.pos.currency.id,
            config_id: this.pos.config.id,
            fiscal_type: this.is_electronic_invoice() ? "electronic" : "internal",
            invoice_journal_id: this.invoice_journal_id || false,
        };
    },
    set_perception: function (percepcion) {
        this.perception_amount = percepcion || 0.0;
        console.log(this.perception_amount);
        //        $('subentry').trigger('change-summary');
        //        $('subentry').trigger('change');
    },
    get_total_perception: function () {
        return this.perception_amount || 0.0;
    },
    get_total_perception_formatted: function () {
        return this.pos.format_currency(this.get_total_perception());
    },
    compute_perceptions: async function () {
        // To avoid restart perception on load values from json
        if (this._on_init_json) {
            return Promise.resolve();
        }
        // To avoid send request
        if (!this.get_partner() || !this.get_orderlines().length) {
            this.set_perception(0);
            return Promise.resolve();
        }
        const order_vals = this._prepare_order_vals();
        const self = this;

        return this.pos.orm
            .call("pos.order", "compute_perceptions", [order_vals])
            .then(function (percepcion) {
                self.set_perception(percepcion);
            });
    },
    // eslint-disable-next-line no-unused-vars
    add_product(product, options) {
        super.add_product(...arguments);
        this.compute_perceptions();
    },

    set_partner(partner) {
        super.set_partner(...arguments);
        this.compute_perceptions();
    },

    get_total_with_tax() {
        let res = super.get_total_with_tax(...arguments);
        res += this.get_total_perception();
        return res;
    },
});
