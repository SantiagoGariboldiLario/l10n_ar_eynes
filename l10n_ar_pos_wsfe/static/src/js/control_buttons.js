/** @odoo-module */

import {ControlButtons} from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import {SelectionPopup} from "@point_of_sale/app/components/popups/selection_popup/selection_popup";
import {makeAwaitable} from "@point_of_sale/app/utils/make_awaitable_dialog";
import {patch} from "@web/core/utils/patch";
import {_t} from "@web/core/l10n/translation";

patch(ControlButtons.prototype, {
    async clickFiscalPosition() {
        const currentFiscalPosition = this.currentOrder?.fiscal_position_id;
        const configFiscalPositions = this.pos.config.fiscal_position_ids || [];
        const loadedFiscalPositions =
            this.pos.models["account.fiscal.position"]?.getAll?.() ||
            this.pos.models["account.fiscal.position"] ||
            [];
        const fiscalPositions = configFiscalPositions.length ? configFiscalPositions : loadedFiscalPositions;

        const fiscalPosList = [
            {
                id: -1,
                label: _t("Original Tax"),
                isSelected: !currentFiscalPosition,
                item: "none",
            },
        ];

        for (const fiscalPos of fiscalPositions) {
            fiscalPosList.push({
                id: fiscalPos.id,
                label: fiscalPos.name || fiscalPos.display_name,
                isSelected: currentFiscalPosition ? fiscalPos.id === currentFiscalPosition.id : false,
                item: fiscalPos,
            });
        }

        const selectedFiscalPosition = await makeAwaitable(this.dialog, SelectionPopup, {
            list: fiscalPosList,
            title: _t("Seleccionar posición fiscal"),
        });

        if (!selectedFiscalPosition) {
            return;
        }

        this.currentOrder.fiscal_position_id =
            selectedFiscalPosition === "none" ? false : selectedFiscalPosition;
        this.currentOrder.triggerRecomputeAllPrices?.();
        if (this.currentOrder.compute_perceptions) {
            await this.currentOrder.compute_perceptions();
            this.currentOrder.triggerRecomputeAllPrices?.();
        }
    },
});
