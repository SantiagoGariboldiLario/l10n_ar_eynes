odoo.define("l10n_ar_pos_wsfe.WSFEPaymentScreen", function (require) {
    "use strict";

    // eslint-disable-next-line no-shadow
    const PaymentScreen = require("point_of_sale.PaymentScreen");
    const Registries = require("point_of_sale.Registries");
    const {isConnectionError} = require("point_of_sale.utils");

    const WSFEPaymentScreen = (PaymentScreen) =>
        class extends PaymentScreen {
            get invoiceNumber() {
                return this.currentOrder.invoiceNumber;
            }
            mounted() {
                super.mounted();
                this.setNextInvoiceSequence();
                this.env.pos.on("change:selectedClient", () => this.setNextInvoiceSequence(), this);
            }
            willUnmount() {
                this.env.pos.off("change:selectedClient", null, this);
            }
            setSequenceValues(seq_vals) {
                if (_.isEmpty(seq_vals)) {
                    this.currentOrder.set_invoice_number();
                    this.currentOrder.set_invoice_journal(false);
                } else {
                    this.currentOrder.set_invoice_number(seq_vals);
                    this.currentOrder.set_invoice_journal(seq_vals.journal_id);
                }
            }
            async setNextInvoiceSequence() {
                const customer = this.currentOrder.get_client();
                if (_.isEmpty(customer)) {
                    this.setSequenceValues();
                    this.render();
                    return;
                }
                const config = this.currentOrder.pos.config;
                const amount_total = this.currentOrder.get_total_with_tax();
                const fiscal_type = this.currentOrder.is_electronic_invoice() ? "electronic" : "internal";
                const move_type = this.currentOrder.get_due() < 0 ? "out_refund" : "out_invoice";
                try {
                    const seq_vals = await this.rpc({
                        model: "account.move",
                        method: "get_next_sequence_from_pos",
                        args: [false, customer.id, config.id, fiscal_type, move_type, amount_total],
                    });
                    this.setSequenceValues(seq_vals);
                    this.render();
                } catch (error) {
                    if (isConnectionError(error)) {
                        await this.showPopup("OfflineErrorPopup", {
                            title: this.env._t("Offline"),
                            body: this.env._t("Unable to get next sequence."),
                        });
                    } else {
                        throw error;
                    }
                }
            }
            checkCustomerSelected() {
                if (!this.currentOrder.get_client()) {
                    this.showPopup("ErrorPopup", {
                        title: this.env._t("Error"),
                        body: this.env._t("You must first select a client."),
                    });
                    return false;
                }
                return true;
            }
            toggleIsManualInvoice() {
                // Click_ship
                if (!this.checkCustomerSelected()) {
                    return;
                }
                if (!this.currentOrder.is_electronic_invoice()) {
                    this.currentOrder.set_manual_invoice(!this.currentOrder.is_manual_invoice());
                    if (this.currentOrder.is_manual_invoice()) {
                        this.setNextInvoiceSequence();
                    } else {
                        this.currentOrder.set_invoice_number();
                    }
                    this.render();
                }
            }
            toggleIsElectronicInvoice() {
                // Click_ship
                if (!this.checkCustomerSelected()) {
                    return;
                }
                if (!this.currentOrder.is_manual_invoice()) {
                    this.currentOrder.set_electronic_invoice(!this.currentOrder.is_electronic_invoice());
                    if (this.currentOrder.is_electronic_invoice()) {
                        this.setNextInvoiceSequence();
                    } else {
                        this.currentOrder.set_invoice_number();
                    }
                    this.render();
                }
            }
        };

    Registries.Component.extend(PaymentScreen, WSFEPaymentScreen);

    return WSFEPaymentScreen;
});
