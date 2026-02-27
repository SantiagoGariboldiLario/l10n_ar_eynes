import logging
from datetime import datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = 'pos.order'

    invoice_journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Invoice Journal',
        copy=False,
    )
    invoice_state = fields.Selection(
        string="Invoice State", related='account_move.state'
    )
    invoice_name = fields.Char(
        string="Invoice Number", related='account_move.name'
    )
    is_wsfe = fields.Boolean(
        string='Is Electronic Invoice',
        copy=False,
    )

    @api.model
    def create_from_ui(self, orders, draft=False):
        def _normalize_id(value):
            if not value:
                return False
            if isinstance(value, int):
                return value
            if isinstance(value, str):
                return int(value) if value.isdigit() else False
            if isinstance(value, (list, tuple)):
                return _normalize_id(value[0]) if value else False
            if isinstance(value, dict):
                return _normalize_id(value.get('id'))
            return False

        PosConfig = self.env['pos.config']
        Partner = self.env['res.partner']
        FiscalPosition = self.env['account.fiscal.position']
        for order in orders:
            data = order.get('data') or {}
            if not data.get('offline'):
                continue
            partner_id = data.get('partner_id')
            config_id = data.get('config_id')
            if not partner_id or not config_id:
                continue
            config = PosConfig.browse(config_id)
            partner = Partner.browse(partner_id)
            order_fiscal_position_id = _normalize_id(
                data.get('fiscal_position_id')
            )
            fiscal_position = (
                FiscalPosition.browse(order_fiscal_position_id)
                if order_fiscal_position_id
                else partner.property_account_position_id
            )
            if (
                fiscal_position
                and fiscal_position.id in config.block_invoice_offline.ids
            ):
                _logger.warning(
                    "POS offline block: order=%s config=%s partner=%s fiscal_position=%s",
                    data.get('name') or order.get('id'),
                    config.display_name,
                    partner.display_name,
                    fiscal_position.display_name,
                )
                raise ValidationError(
                    _(
                        "You cannot validate this order offline because the "
                        "customer fiscal position is configured to block offline "
                        "in this POS."
                    )
                )

        res = super().create_from_ui(orders, draft)
        for order in res:
            state = self.env['account.move'].search_read(
                domain=[('id', '=', order.get('account_move'))],
                fields=['state'],
                load=False,
            )
            if state:
                order.update({'invoice_state': state[0].get('state')})
        return res

    def _export_for_ui(self, order):
        res = super()._export_for_ui(order)
        refunded_move = order.refunded_order_id.account_move
        res['doc_origin'] = (
            refunded_move.get_pretty_sequence() if refunded_move else ''
        )
        return res

    @api.model
    def _order_fields(self, ui_order):
        res = super()._order_fields(ui_order)
        res['invoice_journal_id'] = ui_order.get('invoice_journal_id')
        res['is_wsfe'] = ui_order.get('inv_electronic_mode')
        return res

    def _prepare_invoice_vals(self):
        res = super()._prepare_invoice_vals()
        if self.invoice_journal_id:
            res['journal_id'] = self.invoice_journal_id.id
        fiscal_position = self.partner_id.property_account_position_id
        if fiscal_position:
            res['fiscal_position_id'] = fiscal_position.id
        if (
            self.refunded_order_id.account_move
            and res.get('move_type', '') == 'out_refund'
        ):
            res['associated_inv_ids'] = [
                (6, 0, [self.refunded_order_id.account_move.id])
            ]
        return res

    def _hook_recompute_account_move(self, new_move):
        new_move.add_perceptions()
        new_move._onchange_payment_term_date_invoice()
        new_move.select_default_voucher_type()
        return

    def _check_balanced(self, new_move):
        new_move._check_balanced(self)
        return True

    def _create_invoice(self, move_vals):
        res = super()._create_invoice(move_vals)
        if not self.invoice_journal_id:
            res.sudo().with_company(self.company_id)._onchange_partner()
        self._hook_recompute_account_move(res)
        self._check_balanced(res)
        return res

    def _generate_pos_order_invoice(self):
        moves = self.env['account.move']

        for order in self:
            # Force company for all SUPERUSER_ID action
            if order.account_move:
                moves += order.account_move
                continue

            if not order.partner_id:
                raise UserError(_('Please provide a partner for the sale.'))

            move_vals = order._prepare_invoice_vals()
            new_move = order._create_invoice(move_vals)

            order.write({'account_move': new_move.id})

            # Detect electronic invoice even if the flag from UI is missing:
            is_electronic = (
                order.is_wsfe or new_move.journal_id.fiscal_type == 'electronic'
            )

            if is_electronic:
                res = (
                    new_move.sudo()
                    .with_company(order.company_id)
                    ._validate_electronic_invoices()
                )
                if res is True:
                    moves += new_move
            else:
                new_move.sudo().with_company(order.company_id)._post()
                moves += new_move
                order._reconcile_invoice_payments(
                    new_move,
                    order.payment_ids.mapped('account_move_id'),
                )

        if not moves:
            return {}

        return {
            'name': _('Customer Invoice'),
            'view_mode': 'form',
            'view_id': self.env.ref('account.view_move_form').id,
            'res_model': 'account.move',
            'context': "{'move_type':'out_invoice'}",
            'type': 'ir.actions.act_window',
            'nodestroy': True,
            'target': 'current',
            'res_id': moves and moves.ids[0] or False,
        }

    def _get_computed_account(
        self, product, partner, order_vals, fiscal_position=False
    ):
        fiscal_position = (
            fiscal_position
            if fiscal_position
            else partner.property_account_position_id
        )
        accounts = product.product_tmpl_id.get_product_accounts(
            fiscal_pos=fiscal_position
        )
        account = accounts['income']
        if account:
            return account

        invoice_journal_id = order_vals['invoice_journal_id']
        invoice_journal = self.env['account.journal'].browse(invoice_journal_id)

        if invoice_journal:
            return invoice_journal.default_account_id

        pos_config = self.env['pos.config'].browse(order_vals['config_id'])
        fiscal_type = order_vals['fiscal_type']
        AccountMove = self.env['account.move']
        try:
            invoice_journal = AccountMove.get_journal_from_pos(
                partner,
                fiscal_type,
                pos_config,
            )
        except Exception:
            invoice_journal = self.env['account.journal']
        return invoice_journal.default_account_id

    def _get_perceptions_ctx(self, order_vals):
        return {
            'partner_id': order_vals['partner_id'],
            'invoice_date': order_vals['date'],
            'amount_untaxed': order_vals['untaxed_amount'],
            'order_vals': order_vals,
        }

    @api.model
    def compute_perceptions(self, order_vals):
        partner_id = order_vals.get('partner_id', False)
        if not partner_id:
            return 0.0
        partner = self.env['res.partner'].browse(partner_id)
        fiscal_position = False
        if order_vals.get('fiscal_position_id'):
            fiscal_position = self.env['account.fiscal.position'].browse(
                order_vals['fiscal_position_id']
            )
        else:
            fiscal_position = partner.property_account_position_id
        if order_vals.get('date'):
            order_vals['date'] = datetime.strptime(
                order_vals['date'],
                '%Y-%m-%d',
            ).date()
        date = order_vals['date']

        accounts = {}
        for line in order_vals['order_lines']:
            product = self.env['product.product'].browse(line['product_id'])
            account = self._get_computed_account(
                product, partner, order_vals, fiscal_position=fiscal_position
            )
            if not account:
                raise ValidationError(
                    _(
                        "The product %(product)s has not account configured.",
                        product=product.display_name,
                    )
                )
            accounts.setdefault(account, [])
            accounts[account].append(line)

        perception_application_data = {}
        for account in accounts.keys():
            perceptions_applications = account.get_perceptions_applications(
                fiscal_position
            )
            for application in perceptions_applications:
                account_perception_application_data = (
                    application.get_perception_data(partner, date)
                )
                applicable = application.check_applicable(
                    destination_shipping=partner,
                    source_shipping=self.company_id.partner_id,
                    sit_iibb=account_perception_application_data['sit_iibb'],
                    from_padron=account_perception_application_data[
                        'from_padron'
                    ],
                    excluded_percent=account_perception_application_data[
                        'excluded_percent'
                    ],
                )
                if applicable:
                    perception_application_data.setdefault(
                        application,
                        {'lines': []},
                    )
                    perception_application_data[application].update(
                        account_perception_application_data
                    )
                    perception_application_data[application]['lines'].extend(
                        accounts[account]
                    )

        perceptions_amount = 0.0
        # Se calculan las percepciones obtenidas anteriormente y se generan los correspondientes
        # dicts de datos para crear las líneas de percepción.
        for application in perception_application_data.keys():
            application_data = perception_application_data[application]
            _base, amount = application.apply_perception(application_data)
            perceptions_amount += amount
        return perceptions_amount
