/** @odoo-module */

import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";
import {patch} from "@web/core/utils/patch";
import {_t} from "@web/core/l10n/translation";
import {serializeDateTime} from "@web/core/l10n/dates";
import {AlertDialog} from "@web/core/confirmation_dialog/confirmation_dialog";

// Ensure perceptions/taxes are up-to-date right before validation/receipt
patch(OrderPaymentValidation.prototype, {
    async isOrderValid() {
        const result = await super.isOrderValid(...arguments);
        if (!result) {
            return false;
        }

        const normalizeId = (value) => {
            if (value === undefined || value === null || value === false) {
                return false;
            }
            if (typeof value === "number") {
                return value;
            }
            if (typeof value === "string") {
                const parsed = parseInt(value, 10);
                return Number.isNaN(parsed) ? false : parsed;
            }
            if (Array.isArray(value)) {
                return normalizeId(value[0]);
            }
            if (value?.id !== undefined) {
                return normalizeId(value.id);
            }
            return false;
        };

        const partner = this.order?.getPartner?.();
        const partnerFiscalPositionId = normalizeId(
            partner?.property_account_position_id || this.order?.fiscal_position_id
        );

        if (partner && !partnerFiscalPositionId) {
            this.pos.dialog.add(AlertDialog, {
                title: _t("Missing fields on partner"),
                body: _t("The selected customer needs a fiscal position."),
            });
            return false;
        }

        if (!partner || !partnerFiscalPositionId) {
            return result;
        }

        const blockedFiscalPositions = this.pos.config.block_invoice_offline || [];
        const blockedFiscalPositionIds = blockedFiscalPositions
            .map((item) => normalizeId(item))
            .filter((id) => Boolean(id));

        const blockInvoiceOffline = blockedFiscalPositionIds.includes(partnerFiscalPositionId);
        const isOffline = Boolean(this.pos.data?.network?.offline);
        const cannotComputePerceptions = !this.order.can_compute_perceptions;

        if (blockInvoiceOffline && (isOffline || cannotComputePerceptions)) {
            this.pos.dialog.add(AlertDialog, {
                title: _t("Offline Mode with perceptions"),
                body: _t(
                    "You cannot validate this invoice because it's impossible to get perceptions for this partner."
                ),
            });
            return false;
        }

        return true;
    },

    async finalizeValidation() {
        if (this.order?.compute_perceptions) {
            await this.order.compute_perceptions();
            this.order.triggerRecomputeAllPrices?.();
        }
        if (this.order.isPaidWithCash() || this.order.change) {
            this.pos.hardwareProxy.openCashbox();
        }
        this.order.date_order = serializeDateTime(luxon.DateTime.now());
        for (const line of this.paymentLines) {
            if (line.amount === 0) {
                this.order.removePaymentline(line);
            }
        }
        this.pos.addPendingOrder([this.order.id]);
        this.order.state = "paid";

        try {
            const syncOrderResult = await this.pos.syncAllOrders({throw: true});
            if (!syncOrderResult) {
                return false;
            }

            if (this.shouldDownloadInvoice() && this.order.isToInvoice()) {
                const syncedOrder =
                    syncOrderResult.find((order) => order.uuid === this.order.uuid) || syncOrderResult[0];
                const accountMoveId = syncedOrder?.raw?.account_move || this.order?.raw?.account_move;
                let invoiceState = syncedOrder?.raw?.invoice_state || this.order?.raw?.invoice_state;
                if (accountMoveId && !invoiceState) {
                    const moveData = await this.pos.data.orm.call("account.move", "read", [
                        [accountMoveId],
                        ["state"],
                    ]);
                    invoiceState = moveData?.[0]?.state;
                }

                if (accountMoveId && invoiceState === "posted") {
                    await this.pos.env.services.account_move.downloadPdf(accountMoveId);
                } else if (accountMoveId) {
                    this.pos.dialog.add(AlertDialog, {
                        title: _t("Error with ARCA"),
                        body: _t("Check from backend and solve this situation"),
                    });
                } else {
                    this.pos.dialog.add(AlertDialog, {
                        title: _t("Backend Invoice"),
                        body: _t(
                            "An error occurred while generating an invoice. You can try again from the order list."
                        ),
                    });
                }
            }

            const postPushOrders = syncOrderResult.filter((order) => order.waitForPushOrder());
            if (postPushOrders.length > 0) {
                await this.postPushOrderResolve(postPushOrders.map((order) => order.id));
            }

            return await this.afterOrderValidation(Boolean(syncOrderResult) && syncOrderResult.length > 0);
        } catch (error) {
            return this.handleValidationError(error);
        }
    },
});
