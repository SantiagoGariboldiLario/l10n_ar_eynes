/** @odoo-module **/

import { registry } from "@web/core/registry";
import { SelectionField } from "@web/views/fields/selection/selection_field";

/**
 * Safe selection field to avoid crashes when the stored value is not present
 * in the current selection options (e.g., stale config parameters).
 */
class SafeSelectionField extends SelectionField {
    get string() {
        const value = this.props.record.data[this.props.name];
        if (this.type === "many2one") {
            return value ? value.display_name : "";
        }
        if (this.type === "selection") {
            if (value === false || value === undefined || value === null) {
                return "";
            }
            const option = this.options.find((opt) => opt[0] === value);
            return option ? option[1] : "";
        }
        return "";
    }
}

registry.category("fields").add(
    "selection",
    { component: SafeSelectionField, supportedTypes: ["selection", "many2one"] },
    { force: true }
);
