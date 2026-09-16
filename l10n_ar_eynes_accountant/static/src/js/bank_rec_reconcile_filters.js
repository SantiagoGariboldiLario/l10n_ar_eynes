import {BankRecButtonList} from "@account_accountant/components/bank_reconciliation/button_list/button_list";
import {BankRecSelectCreateDialog} from "@account_accountant/components/bank_reconciliation/search_dialog/search_dialog";
import {patch} from "@web/core/utils/patch";

/**
 * El dialogo "Buscar: Apuntes contables por conciliar" (boton Conciliar del menu
 * de la transaccion) lista todo apunte no conciliado de la compania, sin mirar el
 * diario. Al conciliar un banco eso trae los movimientos de los demas bancos.
 *
 * Sumamos dos filtros por defecto del buscador, no dominios: quedan como
 * etiquetas removibles, asi el usuario las saca cuando la contrapartida vive en
 * otro diario o en otra cuenta (transferencias entre bancos, facturas
 * conciliadas directo contra el extracto).
 *
 *   - el diario de la transaccion
 *   - las cuentas del propio diario: la bancaria y la provisoria
 *
 * Dejamos ademas el agrupado por cuenta disponible en el menu de agrupacion,
 * pero sin activarlo por defecto.
 *
 * Las cuentas van por contexto y no como valor del filtro porque son dos y
 * search_default_<campo> admite una sola. El dominio del filtro
 * journal_accounts lee esa clave (ver views/bank_rec_widget_views.xml).
 *
 * Nos enganchamos en addDialog en lugar de reescribir reconcileOnReconcileLine()
 * para no duplicar el metodo entero y que no se desincronice en cada upgrade.
 * El filtro "sin conciliar" ya viene en getReconcileButtonDomain().
 */
patch(BankRecButtonList.prototype, {
    /**
     * El dominio de core descarta los apuntes conciliados mirando
     * account.move.line.reconciled, que es a nivel apunte. El renglon del banco
     * de una transaccion de extracto nunca se salda contra otro, asi que ese
     * campo queda en false para siempre y la transaccion sigue apareciendo como
     * candidata aunque ya este conciliada.
     *
     * Descartamos tambien por account.bank.statement.line.is_reconciled, que es
     * el estado de la transaccion. Va en el dominio y no como filtro removible
     * porque una transaccion ya conciliada nunca es una contrapartida valida.
     */
    getReconcileButtonDomain() {
        return [
            ...super.getReconcileButtonDomain(),
            "|",
            ["statement_line_id", "=", false],
            ["statement_line_id.is_reconciled", "=", false],
        ];
    },

    setup() {
        super.setup();

        const addDialog = this.addDialog;
        this.addDialog = (DialogClass, props, options) => {
            if (DialogClass !== BankRecSelectCreateDialog) {
                return addDialog(DialogClass, props, options);
            }
            const journal = this.statementLineData.journal_id;
            const accountIds = [journal.default_account_id?.id, journal.suspense_account_id?.id].filter(
                Boolean
            );
            const journalProps = {
                ...props,
                context: {
                    ...props.context,
                    search_default_journal_id: journal.id,
                    bank_rec_journal_account_ids: accountIds,
                    ...(accountIds.length ? {search_default_journal_accounts: 1} : {}),
                },
            };
            return addDialog(DialogClass, journalProps, options);
        };
    },
});
