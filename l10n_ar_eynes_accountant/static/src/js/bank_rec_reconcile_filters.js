import {BankRecButtonList} from "@account_accountant/components/bank_reconciliation/button_list/button_list";
import {BankRecSelectCreateDialog} from "@account_accountant/components/bank_reconciliation/search_dialog/search_dialog";
import {patch} from "@web/core/utils/patch";

/**
 * El dialogo "Buscar: Apuntes contables por conciliar" (boton Conciliar del menu
 * de la transaccion) lista todo apunte no conciliado de la compania, sin mirar el
 * diario. Al conciliar un banco eso trae los movimientos de los demas bancos.
 *
 * Sumamos el diario de la transaccion como filtro por defecto del buscador, no
 * como dominio: queda como etiqueta removible, asi el usuario la saca cuando la
 * contrapartida vive en otro diario (transferencias entre bancos, facturas
 * conciliadas directo contra el extracto).
 *
 * Nos enganchamos en addDialog en lugar de reescribir reconcileOnReconcileLine()
 * para no duplicar el metodo entero y que no se desincronice en cada upgrade.
 * El filtro "sin conciliar" ya viene en getReconcileButtonDomain().
 */
patch(BankRecButtonList.prototype, {
    setup() {
        super.setup();

        const addDialog = this.addDialog;
        this.addDialog = (DialogClass, props, options) => {
            if (DialogClass !== BankRecSelectCreateDialog) {
                return addDialog(DialogClass, props, options);
            }
            const journalProps = {
                ...props,
                context: {
                    ...props.context,
                    search_default_journal_id: this.statementLineData.journal_id.id,
                },
            };
            return addDialog(DialogClass, journalProps, options);
        };
    },
});
