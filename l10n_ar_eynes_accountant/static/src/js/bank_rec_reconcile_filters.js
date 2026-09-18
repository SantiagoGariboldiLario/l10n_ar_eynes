import {BankRecButtonList} from "@account_accountant/components/bank_reconciliation/button_list/button_list";
import {BankRecSelectCreateDialog} from "@account_accountant/components/bank_reconciliation/search_dialog/search_dialog";
import {patch} from "@web/core/utils/patch";

/**
 * El dialogo "Buscar: Apuntes contables por conciliar" (boton Conciliar del menu
 * de la transaccion) lista todo apunte no conciliado de la compania, sin mirar el
 * diario. Al conciliar un banco eso trae los movimientos de los demas bancos.
 *
 * Sumamos la cuenta provisoria del propio diario como filtro por defecto del
 * buscador, no como dominio: queda como etiqueta removible, asi el usuario la
 * saca cuando la contrapartida vive en otra cuenta (transferencias entre
 * bancos, facturas conciliadas directo contra el extracto).
 *
 * No filtramos por diario: el asiento de una transaccion bancaria vive en el
 * diario del banco, pero su contrapartida vive en el diario de la orden de
 * pago, asi que filtrar por diario descarta justamente lo que se busca.
 *
 * Dejamos ademas el agrupado por cuenta disponible en el menu de agrupacion,
 * pero sin activarlo por defecto.
 *
 * La cuenta va por contexto y no como valor de un search_default sobre
 * account_id para poder pasar mas de una si alguna vez hiciera falta. El
 * dominio del filtro journal_accounts lee esa clave (ver
 * views/bank_rec_widget_views.xml).
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
            // Solo la cuenta provisoria: la bancaria nunca es una contrapartida
            // a conciliar, es el propio renglon del extracto.
            const accountIds = [journal.suspense_account_id?.id].filter(Boolean);
            const journalProps = {
                ...props,
                context: {
                    ...props.context,
                    bank_rec_journal_account_ids: accountIds,
                    ...(accountIds.length ? {search_default_journal_accounts: 1} : {}),
                },
            };
            return addDialog(DialogClass, journalProps, options);
        };
    },
});
