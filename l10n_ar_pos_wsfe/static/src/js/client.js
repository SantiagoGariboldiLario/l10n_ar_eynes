odoo.define("l10n_ar_pos_wsfe.ClientDetailsEdit", function (require) {
    "use strict";

    // eslint-disable-next-line no-shadow
    const ClientDetailsEdit = require("point_of_sale.ClientDetailsEdit");
    const Registries = require("point_of_sale.Registries");
    const {_t} = require("web.core");

    const WSFEClientDetailEdit = (ClientDetailsEdit) =>
        class extends ClientDetailsEdit {
            constructor() {
                super(...arguments);
                this.intFields.push("property_account_position_id");
                this.intFields.push("document_type_id");
                this.props.partner.state_id = [];
                const partner = this.props.partner;
                this.changes.property_account_position_id =
                    partner.property_account_position_id && partner.property_account_position_id[0];
                this.changes.document_type_id = partner.document_type_id && partner.document_type_id[0];
            }

            saveChanges() {
                if (
                    !this.props.partner.property_account_position_id &&
                    !this.changes.property_account_position_id
                ) {
                    return this.showPopup("ErrorPopup", {
                        title: _t("Fiscal Position Is Required"),
                    });
                }
                if (!this.props.partner.vat && !this.changes.vat) {
                    return this.showPopup("ErrorPopup", {
                        title: _t("NIF Is Required"),
                    });
                }
                if (!this.props.partner.document_type_id && !this.changes.document_type_id) {
                    return this.showPopup("ErrorPopup", {
                        title: _t("Doc type Is Required"),
                    });
                }
                return super.saveChanges();
            }
        };

    Registries.Component.extend(ClientDetailsEdit, WSFEClientDetailEdit);

    return WSFEClientDetailEdit;
});
