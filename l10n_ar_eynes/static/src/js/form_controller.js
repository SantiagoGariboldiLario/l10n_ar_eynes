// TODO: hacer esto con las notificaciones nativas de v17
// odoo.define("l10n_ar_eynes.FormController", [
//     '@web/FormController', '@web/core'
// ],function (require) {
//     "use strict";

//     var _t = core._t;

//     FormController.include({
//         /**
//          * @private
//          * @override
//          */
//         _confirmSave: function (id) {
//             if (this.modelName === "account.journal") {
//                 let raiseNoDueDateNotification = true;
//                 _.each(this.renderer.allFieldWidgets[id], function (widget) {
//                     if (widget.name === "due_date" && widget.value) {
//                         raiseNoDueDateNotification = false;
//                     }
//                     if (widget.name === "type" && widget.value !== "sale") {
//                         raiseNoDueDateNotification = false;
//                     }
//                 });
//                 if (raiseNoDueDateNotification) {
//                     this.displayNotification({
//                         type: "warning",
//                         title: _t("Warning"),
//                         message: _t("You are creating a journal without Due Date"),
//                         sticky: true,
//                     });
//                 }
//             }
//             return this._super.apply(this, arguments);
//         },
//     });
// });
