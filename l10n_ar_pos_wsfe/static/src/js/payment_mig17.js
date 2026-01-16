/** @odoo-module */

import {PaymentScreen} from "@point_of_sale/app/screens/payment_screen/payment_screen";
import {patch} from "@web/core/utils/patch";
import {ConnectionLostError} from "@web/core/network/rpc_service";
import {_t} from "@web/core/l10n/translation";
import {ErrorPopup} from "@point_of_sale/app/errors/popups/error_popup";
import {PosStore} from "@point_of_sale/app/store/pos_store";

patch(PosStore.prototype, {
    async _processData(loadedData) {
        await super._processData(...arguments);
        this.all_doc_types = loadedData["res.document.type"];
    },

    // _after_flush_orders(orders) {
    //     const res = super._after_flush_orders(...arguments);
    //     console.log("Patched _after_flush_orders called");
    //     for (const order of orders) {
    //         if (this.synch?.status === "disconnected") {
    //             console.log("Setting offline flag for order");
    //             order.data.offline = true;
    //         }
    //     }
    //     return res;
    // },
});

patch(PaymentScreen.prototype, {
    async toggleIsManualInvoice() {
        this.checkCustomerSelected();

        if (this.currentOrder.is_manual_invoice()) {
            this.currentOrder.set_electronic_invoice();
            if (this.currentOrder.is_electronic_invoice()) {
                this.setNextInvoiceSequence();
            } else {
                this.currentOrder.set_invoice_number();
            }
            this.render();
        }
    },

    async toggleIsElectronicInvoice() {
        this.checkCustomerSelected();

        if (this.currentOrder.is_electronic_invoice()) {
            this.currentOrder.set_manual_invoice();
            if (this.currentOrder.is_manual_invoice()) {
                this.setNextInvoiceSequence();
            } else {
                this.currentOrder.set_invoice_number();
            }
            this.render();
        }
    },

    checkCustomerSelected() {
        if (!this.currentOrder.get_partner()) {
            this.env.services.popup.add(ErrorPopup, {
                title: _t("Error"),
                body: _t("You must first select a client."),
            });
        }
    },

    onMounted() {
        super.onMounted();
        // By default set invoice type
        if (this.currentOrder.pos.config.default_invoice_mode == "electronic") {
            this.toggleIsManualInvoice();
        } else {
            this.toggleIsElectronicInvoice();
            this.setNextInvoiceSequence();
        }
    },

    willUnmount() {
        this.env.pos.off("change:selectedClient", null, this);
    },

    setSequenceValues(seq_vals) {
        if (!seq_vals) {
            this.currentOrder.set_invoice_number();
            this.currentOrder.set_invoice_journal(false);
        } else {
            this.currentOrder.set_invoice_number(seq_vals);
            this.currentOrder.set_invoice_journal(seq_vals.journal_id);
        }
    },

    async setNextInvoiceSequence() {
        const customer = this.currentOrder.get_partner();
        if (!customer) {
            this.setSequenceValues();
            this.render();
            return;
        }
        const config = this.currentOrder.pos.config;
        const amount_total = this.currentOrder.get_total_with_tax();
        const fiscal_type = this.currentOrder.is_electronic_invoice() ? "electronic" : "internal";
        const move_type = this.currentOrder._isRefundAndSaleOrder() ? "out_refund" : "out_invoice";
        try {
            const seq_vals = await this.orm.call("account.move", "get_next_sequence_from_pos", [
                false,
                customer.id,
                config.id,
                fiscal_type,
                move_type,
                amount_total,
            ]);
            this.setSequenceValues(seq_vals);
            this.render();
        } catch (error) {
            if (error instanceof ConnectionLostError) {
                // This.env.services.popup.add(ErrorPopup, {
                //     title: _t("Error"),
                //     body: _t("Unable to get next sequence."),
                // });
                this.setSequenceValues();
                this.render();
            } else {
                this.setSequenceValues();
                throw error;
            }
        }
    },

    async selectPartner(isEditMode = false, missingFields = []) {
        await super.selectPartner(isEditMode, missingFields);
        this.setNextInvoiceSequence();
    },

    async _isOrderValid(isForceValidate) {
        let result = super._isOrderValid(isForceValidate);
        const partner = this.currentOrder.get_partner();
        if (partner && !partner.property_account_position_id) {
            this.popup.add(ErrorPopup, {
                title: _t("Missing fields on partner"),
                body: _t("The selected customer needs a fiscal position."),
            });
            result = false;
        }

        let block_invoice_offline = false;
        for (const item of this.currentOrder.pos.config.block_invoice_offline) {
            if (item === partner.property_account_position_id[0]) {
                block_invoice_offline = true;
            }
        }
        if (block_invoice_offline && !this.currentOrder.can_compute_perceptions) {
            this.popup.add(ErrorPopup, {
                title: _t("Offline Mode with perceptions"),
                body: _t(
                    "You cannot validate this invoice because it's impossible to get perceptions for this partner."
                ),
            });
            result = false;
        }
        return result;
    },

    get_invoice_report_action: function () {
        if (this.currentOrder.is_electronic_invoice()) {
            return "l10n_ar_eynes.account_move_report";
        }
        return "l10n_ar_pos_wsfe.account_invoices";
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
        let invoice_state_draft = false;
        try {
            // 1. Save order to server.
            syncOrderResult = await this.pos.push_single_order(this.currentOrder);
            if (!syncOrderResult) {
                return;
            }

            // 2. Invoice.
            if (this.shouldDownloadInvoice()) {
                if (syncOrderResult[0]?.account_move) {
                    if (syncOrderResult[0]?.invoice_state == "draft") {
                        invoice_state_draft = true;
                    } else {
                        await this.report.doAction(this.get_invoice_report_action(), [
                            syncOrderResult[0].account_move,
                        ]);
                    }
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
            }
            throw error;
        } finally {
            this.env.services.ui.unblock();
        }

        // 3. Post process.
        if (syncOrderResult && syncOrderResult.length > 0 && this.currentOrder.wait_for_push_order()) {
            await this.postPushOrderResolve(syncOrderResult.map((res) => res.id));
        }

        await this.afterOrderValidation(Boolean(syncOrderResult) && syncOrderResult.length > 0);

        if (invoice_state_draft) {
            this.env.services.popup.add(ErrorPopup, {
                title: _t("Error with ARCA"),
                body: _t("Check from backend and solve this situation"),
            });
        }
    },
});
