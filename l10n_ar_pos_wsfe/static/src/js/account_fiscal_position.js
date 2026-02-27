/** @odoo-module */

/**
 * Keep taxes when fiscal position has no tax mappings.
 * v19 POS clears taxes if tax_ids is empty; backend override keeps them.
 */
import {patch} from "@web/core/utils/patch";
import {AccountFiscalPosition} from "@point_of_sale/app/models/account_fiscal_position";

// Keep reference to the original method
const _super_getTaxesAfterFiscalPosition = AccountFiscalPosition.prototype.getTaxesAfterFiscalPosition;

patch(AccountFiscalPosition.prototype, {
    getTaxesAfterFiscalPosition(taxes) {
        // If no mappings, keep original taxes (v17 behavior / backend override).
        if (!this.tax_ids?.length) {
            return taxes;
        }
        return _super_getTaxesAfterFiscalPosition.call(this, taxes);
    },
});
