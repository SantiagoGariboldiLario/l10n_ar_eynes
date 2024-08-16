##############################################################################
#
#   Copyright (c) 2022-2023 Eynes SRL  (Eynes - Ingenieria del software)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
#
##############################################################################

import logging

from odoo import _, api, exceptions, fields, models

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _prepare_invoice(self):
        """Overriden to change journal
        for the first mathced journal from user_journal_rel table

        """
        invoice_vals = super()._prepare_invoice()
        invoice_vals.update(
            {'address_shipping_id': self.partner_shipping_id.id}
        )
        journals = self.env.user.get_journals_by_fiscal_position(
            self.fiscal_position_id
        )
        if not journals:
            raise exceptions.ValidationError(
                _(
                    "Could not match any user available journals with fiscal position "
                    "'%(fiscal_pos)s'\n"
                    "Please check if there are any journals with this parameters "
                    "in users > preferences > available journals",
                    fiscal_pos=self.fiscal_position_id.name,
                )
            )
        invoice_vals['journal_id'] = journals[0].id

        date_invoice = fields.Date.today()
        company = self.env.user.company_id
        company_currency = company.currency_id
        currency = self.currency_id
        if currency != company_currency:
            curr_rate = currency._get_currency_rate(company, date_invoice)
            if currency.preciated:
                currency_rate = curr_rate.inverse_company_rate
            else:
                currency_rate = curr_rate.company_rate
        else:
            currency_rate = 1.0

        invoice_vals['currency_rate'] = currency_rate
        return invoice_vals

    @api.model
    def _create_invoices(self, grouped=False, final=False, date=None):
        invoice_ids = super(SaleOrder, self)._create_invoices(
            grouped,
            final,
            date=date,
        )
        ctx = dict(self.env.context)
        ctx['check_move_validity'] = False
        for invoice in invoice_ids:
            invoice._onchange_currency_id()
            invoice._update_perceptions_amounts()
            # invoice._check_balanced()
        return invoice_ids

    def action_confirm(self):
        res = super(SaleOrder, self).action_confirm()
        # carrier_license_id = False
        # trailer_license_id = False

        if self.carrier_id:
            # TODO: Decide how to add this fields to the partner
            # partner = self.carrier_id
            # carrier_license_ids = partner.license_plate_ids
            # trailer_license_ids = partner.trailer_license_plate_ids

            # if carrier_license_ids:
            #     carrier_license_id = carrier_license_ids[0].id
            # if trailer_license_ids:
            #     trailer_license_id = trailer_license_ids[0].id

            self.picking_ids.write(
                {
                    # "license_plate_id": carrier_license_id,
                    # "trailer_license_plate_id": trailer_license_id,
                    "carrier_id": self.carrier_id.id,
                }
            )
        return res
