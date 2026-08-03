from odoo import api, models


class AccountFullReconcile(models.Model):
    _inherit = "account.full.reconcile"

    @api.model_create_multi
    def create(self, vals_list):
        # `full_reconcile_id` se escribe con SQL directo desde
        # `account.full.reconcile.create()`, por lo que no alcanza con
        # extender `account.move.line.write()` para detectar la conciliacion.
        fulls = super().create(vals_list)
        # El core crea el full reconcile con `tracking_disable=True`, y ese
        # contexto llega hasta el write sobre el cheque. Lo reactivamos para
        # que el cambio de estado quede registrado en el chatter.
        for full in fulls.with_context(tracking_disable=False):
            full._update_checks_on_reconcile()
        return fulls

    def _update_checks_on_reconcile(self):
        """Debita/acredita los cheques conciliados contra el extracto bancario.

        Asi el asiento de la conciliacion reemplaza al que generaban los
        wizards de debito/acreditacion, que quedan ocultos en este modulo.
        """
        self.ensure_one()
        lines = self.reconciled_line_ids

        for check in lines.issued_check_id:
            check_move = lines.filtered(
                lambda line: line.issued_check_id == check
            ).move_id
            extract_line = self._get_extract_line(lines, check_move)
            if not extract_line:
                continue
            check.write(
                {
                    'issued_check_state': 'debited',
                    'clearance_move_id': extract_line.move_id.id,
                    'deposit_date': extract_line.date,
                    'deposit_bank_id': check.checkbook_id.bank_account_id.id,
                }
            )

        third_checks = self.env['account.check'].search(
            [('deposit_move_id', 'in', lines.move_id.ids)]
        )
        for check in third_checks:
            extract_line = self._get_extract_line(lines, check.deposit_move_id)
            if not extract_line:
                continue
            check.write(
                {
                    'third_party_check_state': 'accredited',
                    'accredit_move_id': extract_line.move_id.id,
                    'accredit_date': extract_line.date,
                }
            )

    def _get_extract_line(self, lines, check_move):
        """Linea del extracto bancario dentro de la conciliacion.

        Es la que no pertenece al asiento propio del cheque y no esta
        asociada a ningun cheque emitido.
        """
        return next(
            (
                line
                for line in lines
                if line.move_id != check_move and not line.issued_check_id
            ),
            None,
        )
