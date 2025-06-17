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
