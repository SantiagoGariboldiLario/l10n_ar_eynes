odoo.define("l10n_ar_pos_wsfe.PosOrder", function (require) {
    "use strict";

    var models = require("point_of_sale.models");

    models.load_fields("res.partner", ["property_account_position_id"]);

    models.load_models([
        {
            model: "account.fiscal.position",
            label: "load_all_fiscal_position",
            fields: [],
            loaded: function (self, fiscal_positions) {
                self.all_fiscal_positions = fiscal_positions;
            },
        },
    ]);

    // Var _super_posmodel = models.PosModel.prototype;
    models.PosModel = models.PosModel.extend({
        get_invoice_report_action: function () {
            return "l10n_ar_eynes.account_move_report";
        },

        push_and_invoice_order: function (order) {
            var self = this;
            return new Promise((resolve, reject) => {
                if (!order.get_client()) {
                    reject({code: 400, message: "Missing Customer", data: {}});
                } else {
                    var order_id = self.db.add_order(order.export_as_JSON());
                    self.flush_mutex.exec(async () => {
                        try {
                            const server_ids = await self._flush_orders([self.db.get_order(order_id)], {
                                timeout: 30000,
                                to_invoice: true,
                            });
                            if (server_ids.length) {
                                const [orderWithInvoice] = await self.rpc({
                                    method: "read",
                                    model: "pos.order",
                                    args: [server_ids, ["account_move"]],
                                    kwargs: {load: false},
                                });
                                const report_name = self.get_invoice_report_action();
                                await self
                                    .do_action(report_name, {
                                        additional_context: {
                                            active_ids: [orderWithInvoice.account_move],
                                        },
                                    })
                                    .catch(() => {
                                        reject({code: 401, message: "Backend Invoice", data: {order: order}});
                                    });
                            } else {
                                reject({code: 401, message: "Backend Invoice", data: {order: order}});
                            }
                            resolve(server_ids);
                        } catch (error) {
                            reject(error);
                        }
                    });
                }
            });
        },
    });

    var _super_order = models.Order.prototype;
    models.Order = models.Order.extend({
        /* ---- Invoice --- */
        initialize: function () {
            _super_order.initialize.apply(this, arguments);
            this.invoiceNumber = "";
            this.inv_manual_mode = false;
            this.inv_electronic_mode = true;
            this.to_invoice = true;
            return this;
        },
        set_invoice_number: function (seq_vals) {
            if (_.isEmpty(seq_vals)) {
                this.invoiceNumber = "";
                return;
            }
            const number = seq_vals.next_seq;
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
            var json = _super_order.export_as_JSON.apply(this, arguments);
            json.inv_manual_mode = this.inv_manual_mode ? this.inv_manual_mode : false;
            json.inv_electronic_mode = this.inv_electronic_mode ? this.inv_electronic_mode : false;
            json.invoice_journal_id = this.invoice_journal_id || false;
            json.doc_origin = this.doc_origin;
            return json;
        },
        // eslint-disable-next-line no-unused-vars
        init_from_JSON: function (json) {
            _super_order.init_from_JSON.apply(this, arguments);
            this.inv_manual_mode = false;
            this.inv_electronic_mode = true;
            this.to_invoice = true;
            this.invoice_journal_id = false;
            this.doc_origin = json.doc_origin || "";
        },
    });
});
