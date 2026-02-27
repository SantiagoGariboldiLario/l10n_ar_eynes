/** @odoo-module */

import {AccountMoveService} from "@account/services/account_move_service";
import {patch} from "@web/core/utils/patch";
import {_t} from "@web/core/l10n/translation";
import {AlertDialog} from "@web/core/confirmation_dialog/confirmation_dialog";

patch(AccountMoveService.prototype, {
    async downloadPdf(accountMoveId, target = "download") {
        const data = await this.orm.call("account.move", "get_pos_invoice_download_data", [accountMoveId]);
        if (data?.state !== "posted") {
            this.dialog.add(AlertDialog, {
                title: _t("Error with ARCA"),
                body: _t("Check from backend and solve this situation"),
            });
            return;
        }
        const reportService = this.env?.services?.report;
        if (data?.report_action && reportService?.doAction) {
            await reportService.doAction(data.report_action, [accountMoveId]);
            return;
        }
        return await super.downloadPdf(accountMoveId, target);
    },
});
