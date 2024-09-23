/** @odoo-module */

import {PartnerDetailsEdit} from "@point_of_sale/app/screens/partner_list/partner_editor/partner_editor";
import {patch} from "@web/core/utils/patch";
import {ErrorPopup} from "@point_of_sale/app/errors/popups/error_popup";
import {_t} from "@web/core/l10n/translation";

patch(PartnerDetailsEdit.prototype, {
    setup() {
        super.setup(...arguments);
        this.intFields.push("property_account_position_id");
        this.intFields.push("document_type_id");
        this.props.partner.state_id = [];
        const partner = this.props.partner;
        this.changes.property_account_position_id =
            partner.property_account_position_id && partner.property_account_position_id[0];
        this.changes.document_type_id = partner.document_type_id && partner.document_type_id[0];
    },
    saveChanges() {
        if (!this.props.partner.property_account_position_id && !this.changes.property_account_position_id) {
            this.env.services.popup.add(ErrorPopup, {
                title: _t("Error"),
                body: _t("Fiscal Position Is Required"),
            });
            return false;
        }
        if (!this.props.partner.document_type_id && !this.changes.document_type_id) {
            this.env.services.popup.add(ErrorPopup, {
                title: _t("Error"),
                body: _t("Doc Type Required"),
            });
            return false;
        }
        if (!this.props.partner.vat && !this.changes.vat) {
            this.env.services.popup.add(ErrorPopup, {
                title: _t("Error"),
                body: _t("NIF Required"),
            });
            return false;
        }
        return super.saveChanges();
    },
});
