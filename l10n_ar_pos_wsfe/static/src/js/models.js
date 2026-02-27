/** @odoo-module */

import {PosOrder} from "@point_of_sale/app/models/pos_order";
import {patch} from "@web/core/utils/patch";
import {ConnectionLostError} from "@web/core/network/rpc";
import {AlertDialog} from "@web/core/confirmation_dialog/confirmation_dialog";
import {_t} from "@web/core/l10n/translation";
import {PosStore} from "@point_of_sale/app/services/pos_store";
import {PosOrderline} from "@point_of_sale/app/models/pos_order_line";

patch(PosOrder.prototype, {
    setup(vals) {
        super.setup(vals);
        this.invoiceNumber = "";
        this.inv_electronic_mode = false;
        this.to_invoice = true;
        this.invoice_journal_id = false;
        this.perception_amount = 0.0;
        this.partner_final_consumer = false;
        this.can_compute_perceptions = true;
        if (!this.data && this.model?.models?.data) {
            this.data = this.model.models.data;
        }
        // Ensure fiscal position is set (v19 sometimes leaves it undefined on load)
        if (!this.fiscal_position_id) {
            this.fiscal_position_id = this.config?.default_fiscal_position_id || null;
            this.triggerRecomputeAllPrices?.();
        }
    },
    _isRefundAndSaleOrder: function () {
        return this.getHasRefundLines();
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
    set_manual_invoice: function () {
        this.assertEditable();
        this.inv_electronic_mode = false;
    },
    is_manual_invoice: function () {
        return !this.inv_electronic_mode;
    },
    set_electronic_invoice: function () {
        this.assertEditable();
        this.inv_electronic_mode = true;
    },
    is_electronic_invoice: function () {
        return this.inv_electronic_mode;
    },
    set_invoice_journal: function (journal_id) {
        this.invoice_journal_id = journal_id;
    },
    export_as_JSON() {
        var json = super.export_as_JSON(...arguments);
        const defaultElectronic = this.pos?.config?.default_invoice_mode === "electronic";
        const invElectronic =
            this.inv_electronic_mode !== undefined ? this.inv_electronic_mode : defaultElectronic;
        json.inv_electronic_mode = Boolean(invElectronic);
        json.invoice_journal_id = this.invoice_journal_id || false;
        json.to_invoice = true;
        json.offline = Boolean(this.pos?.data?.network?.offline);
        json.doc_origin = this.doc_origin || "";
        json.partner_final_consumer = this.partner_final_consumer;
        json.can_compute_perceptions = this.can_compute_perceptions;
        json.perception_amount = this.perception_amount || 0.0;
        return json;
    },

    init_from_JSON(json) {
        this._on_init_json = true;
        super.init_from_JSON(...arguments);
        this._on_init_json = false;
        const defaultElectronic = this.config?.default_invoice_mode === "electronic";
        this.inv_electronic_mode =
            json.inv_electronic_mode !== undefined ? json.inv_electronic_mode : defaultElectronic;
        this.to_invoice = true;
        this.invoice_journal_id = false;
        this.doc_origin = json.doc_origin || "";
        this.partner_final_consumer = json.partner_final_consumer || false;
        this.can_compute_perceptions =
            json.can_compute_perceptions !== undefined ? json.can_compute_perceptions : true;
        this.perception_amount = json.perception_amount || 0.0;
        if (!this.data && this.model?.models?.data) {
            this.data = this.model.models.data;
        }
        if (!this.fiscal_position_id) {
            this.fiscal_position_id = this.config?.default_fiscal_position_id || null;
            this.triggerRecomputeAllPrices?.();
        }
        this.compute_perceptions();
    },

    /* -- Percepcions -- */
    _prepare_lines_to_compute_perception() {
        return this.getOrderlines()
            .filter((line) => line.product_id) // Safety: skip lines without product
            .map((line) => ({
                product_id: line.product_id.id,
                qty: typeof line.getQuantity === "function" ? line.getQuantity() : line.qty || 0,
                price: line.price_unit || 0,
                tax_ids: line.tax_ids || line.product_id.taxes_id || [],
                discount: line.discount || 0,
                price_subtotal: line.priceExcl,
                price_total: line.priceIncl,
            }));
    },
    _prepare_order_vals: function () {
        const partner = this.getPartner();
        let date = false;
        if (this.creation_date) {
            date = this.creation_date.toISOString().slice(0, 10);
        }
        const fiscal_position_id =
            this.fiscal_position_id?.id || partner?.property_account_position_id?.id || false;
        return {
            partner_id: partner ? partner.id : false,
            date: date || false,
            untaxed_amount: this.priceExcl,
            tax_amount: this.amountTaxes,
            invoice_type: this._isRefundAndSaleOrder() ? "out_refund" : "out_invoice",
            order_lines: this._prepare_lines_to_compute_perception(),
            currency_id: this.currency.id,
            config_id: this.config.id,
            fiscal_type: this.is_electronic_invoice() ? "electronic" : "internal",
            invoice_journal_id: this.invoice_journal_id || false,
            fiscal_position_id,
        };
    },
    set_perception: function (percepcion) {
        this.perception_amount = percepcion || 0.0;
        // Force recompute of cached prices and notify reactive system
        this.triggerRecomputeAllPrices?.();
        this._markDirty?.();
    },
    get_total_perception: function () {
        return this.perception_amount || 0.0;
    },
    get_total_perception_formatted: function () {
        // In v19, models don't have access to this.pos
        // The template will format the currency using env.utils.formatCurrency
        return this.get_total_perception();
    },
    compute_perceptions: async function () {
        if (this._on_init_json) {
            return Promise.resolve();
        }
        if (!this.data) {
            return Promise.resolve();
        }
        const partner = this.getPartner();
        const lines = this.getOrderlines();
        if (!partner || !lines.length) {
            this.set_perception(0);
            return Promise.resolve();
        }
        const order_vals = this._prepare_order_vals();
        // Debounce/concurrency control
        this._perceptionStamp = (this._perceptionStamp || 0) + 1;
        const stamp = this._perceptionStamp;
        try {
            const amount = await this.data.orm.call("pos.order", "compute_perceptions", [order_vals]);
            if (stamp !== this._perceptionStamp) {
                return;
            }
            this.set_perception(amount);
            this.can_compute_perceptions = true;
        } catch (error) {
            if (stamp !== this._perceptionStamp) {
                return;
            }
            if (error instanceof ConnectionLostError) {
                this.can_compute_perceptions = false;
                this.set_perception(0);
            } else {
                throw error;
            }
        }
    },
    _over_final_consumer_max_amount: function () {
        if (this.is_electronic_invoice() && this.partner_final_consumer) {
            const total = this.priceIncl;
            const self = this;
            this.data.orm.call("res.company", "get_fc_max_amount", [this.company.id]).then(function (max_fc) {
                if (total > max_fc) {
                    self.dialog.add(AlertDialog, {
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
        if (!this.fiscal_position_id) {
            this.fiscal_position_id = this.config?.default_fiscal_position_id || null;
            this.triggerRecomputeAllPrices?.();
        }
        this.compute_perceptions();
        if (partner) {
            const self = this;
            this.data.orm
                .call("res.partner", "check_final_consumer_without_vat", [partner.id])
                .then(function (result) {
                    self.partner_final_consumer = result;
                    self._over_final_consumer_max_amount();
                });
        } else {
            this.partner_final_consumer = false;
        }
    },

    get priceIncl() {
        let res = super.priceIncl;
        res += this.get_total_perception();
        return res;
    },
    get totalDue() {
        // Include perceptions in amount to pay
        const base = super.totalDue;
        return this.currency.round(base + this.get_total_perception());
    },
});

// Patch POS Store to trigger perception recompute on partner/product changes
patch(PosStore.prototype, {
    async setup(env, deps) {
        const res = await super.setup(env, deps);
        this._l10n_ar_attachDataAndRecompute();
        return res;
    },

    _l10n_ar_attachDataAndRecompute() {
        const data = this.data;
        if (!data) {
            return;
        }
        const orders = this.models["pos.order"]?.getAll?.() || [];
        orders.forEach((order) => {
            order.data = data;
            if (order.compute_perceptions) {
                order.compute_perceptions();
            }
        });
    },

    async addLineToOrder(vals, order) {
        // Avoid multiple recomputes during merge; compute once after super
        order._suppress_perception = true;
        const res = await super.addLineToOrder(...arguments);
        order._suppress_perception = false;
        if (order?.compute_perceptions) {
            order.data = this.data; // Provide rpc service to PosOrder
            order.compute_perceptions();
        }
        return res;
    },

    setPartnerToCurrentOrder() {
        const res = super.setPartnerToCurrentOrder(...arguments);
        const order = this.getOrder();
        if (order?.compute_perceptions) {
            order.data = this.data; // Provide rpc service to PosOrder
            order.compute_perceptions();
        }
        return res;
    },
});

// Patch order line price change to recompute perceptions when price is edited
patch(PosOrderline.prototype, {
    setUnitPrice() {
        const res = super.setUnitPrice(...arguments);
        const order = this.order_id;
        if (order?._suppress_perception) {
            return res;
        }
        if (order?.compute_perceptions) {
            // Ensure rpc service is available
            if (!order.data && order.model?.models?.data) {
                order.data = order.model.models.data;
            }
            order.compute_perceptions();
        }
        return res;
    },
});

// Recompute taxes/prices when FP or pricelist changes (e.g., after selecting partner)
patch(PosOrder.prototype, {
    updatePricelistAndFiscalPosition() {
        const res = super.updatePricelistAndFiscalPosition(...arguments);
        this.triggerRecomputeAllPrices?.();
        return res;
    },
});
