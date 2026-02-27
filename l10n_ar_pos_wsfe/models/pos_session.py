from odoo import _, models
from odoo.exceptions import UserError


class PosSession(models.Model):
    _inherit = 'pos.session'

    def _check_invoices_are_posted(self):
        unposted_invoices = (
            self._get_closed_orders()
            .sudo()
            .with_company(self.company_id)
            .account_move.filtered(lambda x: x.state != 'posted')
        )
        if unposted_invoices:
            raise UserError(
                _(
                    'You cannot close the POS when invoices are not posted.\n'
                    'Go to Orders --> Orders, and use the Draft Invoices filter to fix it.'
                )
            )

    def _is_capture_system_activated(self):
        """Override because native method needs ir_config_parameter that doesn't exists and it must be
        created by point_of_sale module
        """
        return True

    def _check_pos_receivable_accounts_configuration(self):
        for session in self:
            if session.company_id.account_default_pos_receivable_account_id:
                continue
            used_payment_methods = (
                session._get_closed_orders().payment_ids.payment_method_id
            )
            missing_accounts = used_payment_methods.filtered(
                lambda pm: not pm.split_transactions
                and not pm.receivable_account_id
            )
            if missing_accounts:
                raise UserError(
                    _(
                        "Cannot close POS session %(session)s.\n"
                        "The company has no 'Default PoS Receivable Account' and these payment methods "
                        "also have no receivable account: %(methods)s.\n"
                        "Configure one of them in Accounting settings or on each payment method.",
                        session=session.display_name,
                        methods=", ".join(missing_accounts.mapped("name")),
                    )
                )

    def action_pos_session_validate(
        self,
        balancing_account=False,
        amount_to_balance=0,
        bank_payment_method_diffs=None,
    ):
        self._check_pos_receivable_accounts_configuration()
        return super().action_pos_session_validate(
            balancing_account=balancing_account,
            amount_to_balance=amount_to_balance,
            bank_payment_method_diffs=bank_payment_method_diffs,
        )

    def _loader_params_account_fiscal_position(self):
        domain = [('active', '=', True)]
        if self.config_id.tax_regime_selection:
            domain = [('id', 'in', self.config_id.fiscal_position_ids.ids)]
        return {
            'search_params': {
                'domain': domain,
                'fields': ['id', 'name', 'tax_ids'],
            }
        }

    def _loader_params_res_partner(self):
        result = super()._loader_params_res_partner()
        result['search_params']['fields'].append('property_account_position_id')
        result['search_params']['fields'].append('document_type_id')
        return result

    def _pos_ui_models_to_load(self):
        res = super()._pos_ui_models_to_load()
        res.append('res.document.type')
        return res

    def _loader_params_res_document_type(self):
        return {
            'search_params': {
                'domain': [(1, '=', 1)],
                'fields': ['id', 'name'],
            },
        }

    def _get_pos_ui_res_document_type(self, params):
        return self.env['res.document.type'].search_read(
            **params['search_params']
        )
