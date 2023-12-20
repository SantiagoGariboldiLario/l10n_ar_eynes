odoo.define("l10n_ar_pos_wsfe.PosOrder", function (require) {
    "use strict";

    var models = require("point_of_sale.models");

    var _super_order = models.Order.prototype;
    models.Order = models.Order.extend({
        /* ---- Invoice --- */
        initialize: function () {
            _super_order.initialize.apply(this, arguments);
            this.invoiceNumber = "";
            return this;
        },
        set_invoice_number: function (number) {
            if (!number) {
                this.invoiceNumber = "";
            } else {
                this.invoiceNumber = `[ ${number} ]`;
            }
        },
        set_manual_invoice: function (manual_mode) {
            this.assert_editable();
            this.inv_manual_mode = manual_mode;
        },
        is_manual_invoice: function () {
            return this.inv_manual_mode;
        },
        set_electronic_invoice: function (electronic_mode) {
            this.assert_editable();
            this.inv_electronic_mode = electronic_mode;
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
            return json;
        },
        // eslint-disable-next-line no-unused-vars
        init_from_JSON: function (json) {
            _super_order.init_from_JSON.apply(this, arguments);
            this.inv_manual_mode = false;
            this.inv_electronic_mode = false;
            this.invoice_journal_id = false;
        },
    });
});
