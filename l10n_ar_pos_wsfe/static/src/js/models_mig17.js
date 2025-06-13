/** @odoo-module */

import {Order} from "@point_of_sale/app/store/models";
import {PaymentScreen} from "@point_of_sale/app/screens/payment_screen/payment_screen";
import {patch} from "@web/core/utils/patch";
import {useService} from "@web/core/utils/hooks";
import {ConnectionLostError} from "@web/core/network/rpc_service";
import {ErrorPopup} from "@point_of_sale/app/errors/popups/error_popup";
import {_t} from "@web/core/l10n/translation";

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
        this.partner_final_consumer = false;
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
    getInvoiceNumber: function () {
        return this.invoiceNumber;
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
    export_as_JSON() {
        var json = super.export_as_JSON(...arguments);
        json.inv_manual_mode = this.inv_manual_mode ? this.inv_manual_mode : false;
        json.inv_electronic_mode = this.inv_electronic_mode ? this.inv_electronic_mode : false;
        json.invoice_journal_id = this.invoice_journal_id || false;
        json.doc_origin = this.doc_origin || "";
        json.partner_final_consumer = this.partner_final_consumer;
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
        this.partner_final_consumer = json.partner_final_consumer || false;
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
    },
    get_total_perception: function () {
        return this.perception_amount || 0.0;
    },
    get_total_perception_formatted: function () {
        return this.pos.format_currency(this.get_total_perception());
    },
    compute_perceptions: async function () {
        if (this._on_init_json) {
            return Promise.resolve();
        }
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
    _over_final_consumer_max_amount: function () {
        if (this.is_electronic_invoice() && this.partner_final_consumer) {
            const total = this.get_total_with_tax();
            const self = this;
            this.pos.orm
                .call("res.company", "get_fc_max_amount", [this.pos.company.id])
                .then(function (max_fc) {
                    if (total > max_fc) {
                        self.pos.env.services.popup.add(ErrorPopup, {
                            title: _t("Error"),
                            body: _t("You must inform Final Consumer data to ARCA, create new Customer"),
                        });
                        self.set_partner(false);
                    }
                });
        }
    },
    // eslint-disable-next-line no-unused-vars
    async add_product(product, options) {
        super.add_product(...arguments);
        this.compute_perceptions();
        this._over_final_consumer_max_amount();
    },

    set_partner(partner) {
        super.set_partner(...arguments);
        this.compute_perceptions();
        if (partner) {
            const self = this;
            this.pos.orm
                .call("res.partner", "check_final_consumer_without_vat", [partner.id])
                .then(function (result) {
                    self.partner_final_consumer = result;
                    self._over_final_consumer_max_amount();
                });
        } else {
            this.partner_final_consumer = false;
        }
    },

    get_total_with_tax() {
        let res = super.get_total_with_tax(...arguments);
        res += this.get_total_perception();
        return res;
    },
});

patch(PaymentScreen.prototype, {
    get_invoice_report_action: function () {
        return "l10n_ar_eynes.account_move_report";
    },

    async _finalizeValidation() {
        if (this.currentOrder.is_paid_with_cash() || this.currentOrder.get_change()) {
            this.hardwareProxy.openCashbox();
        }

        this.currentOrder.date_order = luxon.DateTime.now();
        for (const line of this.paymentLines) {
            if (!line.amount === 0) {
                this.currentOrder.remove_paymentline(line);
            }
        }
        this.currentOrder.finalized = true;

        this.env.services.ui.block();
        let syncOrderResult;
        try {
            // 1. Save order to server.
            syncOrderResult = await this.pos.push_single_order(this.currentOrder);
            if (!syncOrderResult) {
                return;
            }
            // 2. Invoice.
            if (this.shouldDownloadInvoice()) {
                if (syncOrderResult[0]?.account_move) {
                    await this.report.doAction(this.get_invoice_report_action(), [
                        syncOrderResult[0].account_move,
                    ]);
                } else {
                    throw {
                        code: 401,
                        message: "Backend Invoice",
                        data: {order: this.currentOrder},
                    };
                }
            }
        } catch (error) {
            if (error instanceof ConnectionLostError) {
                this.pos.showScreen(this.nextScreen);
                Promise.reject(error);
                return error;
            } else {
                throw error;
            }
        } finally {
            this.env.services.ui.unblock();
        }

        // 3. Post process.
        if (syncOrderResult && syncOrderResult.length > 0 && this.currentOrder.wait_for_push_order()) {
            await this.postPushOrderResolve(syncOrderResult.map((res) => res.id));
        }

        await this.afterOrderValidation(!!syncOrderResult && syncOrderResult.length > 0);
    },
});
