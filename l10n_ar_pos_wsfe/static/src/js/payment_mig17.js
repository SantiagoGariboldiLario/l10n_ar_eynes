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
                this.env.services.popup.add(ErrorPopup, {
                    title: _t("Error"),
                    body: _t("Unable to get next sequence."),
                });
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
        return result;
    },
});
