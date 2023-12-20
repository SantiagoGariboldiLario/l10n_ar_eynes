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
            async setNextInvoiceSequence() {
                const customer = this.currentOrder.get_client();
                const config = this.currentOrder.pos.config;
                const amount_total = this.currentOrder.get_total_with_tax();
                const fiscal_type = this.currentOrder.is_electronic_invoice() ? "electronic" : "internal";
                try {
                    const seq_vals = await this.rpc({
                        model: "account.move",
                        method: "get_next_sequence_from_pos",
                        args: [
                            this.env.pos.pos_session.id,
                            customer.id,
                            config.id,
                            fiscal_type,
                            amount_total,
                        ],
                    });
                    this.currentOrder.set_invoice_number(seq_vals.next_seq);
                    this.currentOrder.set_invoice_journal(seq_vals.journal_id);
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
                    const is_manual_invoice = this.currentOrder.is_manual_invoice();
                    this.currentOrder.set_to_invoice(is_manual_invoice);
                    if (is_manual_invoice) {
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
                    const is_electronic_invoice = this.currentOrder.is_electronic_invoice();
                    this.currentOrder.set_to_invoice(is_electronic_invoice);
                    if (is_electronic_invoice) {
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
