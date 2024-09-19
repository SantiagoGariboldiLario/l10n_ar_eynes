import logging
from ast import literal_eval

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ResPartnerAfipPadron(models.TransientModel):
    _name = "res.partner.afip.padron.fields"
    _description = "AFIP Padron Fields"

    wizard_id = fields.Many2one(
        "res.partner.afip.padron.wizard",
        "Wizard",
    )
    field = fields.Char("name")
    old_value = fields.Char()
    new_value = fields.Char()
    new_value_id = fields.Char()


class ResPartnerAfipPadronWizard(models.TransientModel):
    _name = "res.partner.afip.padron.wizard"
    _inherit = ["multi.step.wizard.mixin"]
    _description = "AFIP Padron Wizard"

    field_ids = fields.One2many(
        "res.partner.afip.padron.fields",
        "wizard_id",
        string="Fields",
    )
    partner_ids = fields.Many2many(
        "res.partner",
        "partner_update_from_padron_eynes_rel",
        "update_id",
        "partner_id",
        string="Partners",
        default=lambda self: self.get_partners(),
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Partner",
        readonly=True,
        default=lambda self: self.env.context.get('active_id'),
    )
    case_convertion = fields.Selection(
        [
            ('title', 'Titlecase'),
            ('lower', 'Lowercase'),
            ('upper', 'Uppercase'),
            ('capitalize', 'Capitalize'),
        ],
        help="Converts AFIP data to specific case.",
        default=lambda self: self.get_default_case(),
    )
    field_to_update_ids = fields.Many2many(
        "ir.model.fields",
        "res_partner_update_fields",
        "update_id",
        "field_id",
        string="Fields To Update",
        help="Fields to be retrived and updated",
        default=lambda self: self.get_fields(),
        domain=lambda self: self.get_fields_domain(),
    )

    @api.model
    def get_fields(self):
        return self.env["ir.model.fields"].search(self.get_fields_domain())

    @api.model
    def get_fields_domain(self):
        fields_names = [
            "name",
            "street",
            "city",
            "zip",
            "state_id",
            "country_id",
            "property_account_position_id",
        ]
        return [
            ("model", "=", "res.partner"),
            ("name", "in", fields_names),
        ]

    @api.model
    def get_default_case(self):
        default_case = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("l10n_ar_eynes.case_convertion")
            or 'title'
        )
        return default_case

    @api.model
    def default_get(self, default_fields):
        res = super().default_get(default_fields)
        context = self._context
        res["state"] = "final"
        if context.get("active_model") == "res.partner":
            active_ids = context.get("active_ids")
            partners = self.get_partners()
            partners_count = len(partners)
            if len(active_ids) >= 1 and partners_count == 1:
                res["state"] = "single_update"
                res["partner_id"] = partners[0].id
            elif len(active_ids) > 1 and partners_count > 1:
                res["state"] = "mass_configuration"
        return res

    @api.model
    def get_partners(self):
        if not self.partner_ids:
            active_ids = self._context.get("active_ids", [])
            domain = [
                ("vat", "!=", False),
                ("document_type_id.afip_code", "=", 80),
            ]
            if active_ids:
                domain.append(("id", "in", active_ids))
            partners = self.env["res.partner"].search(domain)
            return partners

    def _change_text_case(self, new_value):
        if self.case_convertion == 'title':
            new_value = new_value and new_value.title()
        if self.case_convertion == 'lower':
            new_value = new_value and new_value.lower()
        if self.case_convertion == 'upper':
            new_value = new_value and new_value.upper()
        if self.case_convertion == 'capitalize':
            new_value = new_value and new_value.capitalize()
        return new_value

    @api.onchange("partner_id")
    def change_partner(self):
        self.ensure_one()
        self.field_ids.unlink()
        partner = None
        if self.partner_id.vat:
            partner = self.partner_id
        fields_names = self.field_to_update_ids.mapped("name")
        if partner:
            partner_vals = partner.get_data_from_padron_afip()
            lines = []
            fields_names = list(set(partner_vals) & set(fields_names))
            for key in fields_names:
                new_value_id = False
                old_value = partner[key]
                new_value = partner_vals[key]
                if new_value == "":
                    new_value = False
                if key in ("name", "city", "street"):
                    new_value = self._change_text_case(new_value)
                if key in ("impuestos_padron", "actividades_padron"):
                    old_value = old_value.ids
                elif key in (
                    "state_id",
                    "property_account_position_id",
                    "country_id",
                ):
                    if key == 'country_id':
                        _model = 'res.country'
                    elif key == 'state_id':
                        _model = 'res.country.state'
                    elif key == 'property_account_position_id':
                        _model = 'account.fiscal.position'
                    new_value = (
                        self.sudo().env[_model].browse(new_value)
                    )  # skip security rules
                    new_value_id = new_value.id
                    new_value = new_value.name
                    old_value = old_value.sudo().name  # skip security rules
                if new_value and key in fields_names and old_value != new_value:
                    line_vals = {
                        "wizard_id": self.id,
                        "field": key,
                        "old_value": old_value,
                        "new_value": new_value,
                        "new_value_id": new_value_id,
                    }
                    lines.append((0, False, line_vals))
            self.field_ids = lines

    @api.model
    def _selection_state(self):
        return [
            ('mass_configuration', 'Mass Update Configuration'),
            ('single_update', 'Single Update'),
            ('single_partner_updated', 'Single Partner Updated'),
            ('final', 'Final'),
        ]

    def state_exit_mass_configuration(self):
        self.state = 'single_update'

    def state_exit_single_update(self):
        if self.partner_id:
            self.write({"partner_ids": [(3, self.partner_id.id, False)]})
        if self.partner_ids:
            partner = self.partner_ids[0]
            self.write(
                {
                    "partner_id": partner.id,
                    "state": "single_update",
                }
            )
            self.change_partner()
        else:
            self.write(
                {
                    "state": "final",
                }
            )
        return self._reopen_self()

    def open_next(self):
        """Method to Skip the Partner"""
        self.ensure_one()
        state_method = getattr(self, f"state_exit_{self.state}", None)
        state_method()
        return self._reopen_self()

    def _update(self):
        self.ensure_one()
        vals = {}
        for field in self.field_ids:
            if field.field in ("impuestos_padron", "actividades_padron"):
                vals[field.field] = [(6, False, literal_eval(field.new_value))]
            elif field.field in (
                "state_id",
                "property_account_position_id",
                "country_id",
            ):
                vals[field.field] = literal_eval(field.new_value_id)
            else:
                vals[field.field] = field.new_value
        vals["last_update_from_afip"] = fields.Date.today()
        self.partner_id.write(vals)

    def update_selected(self):
        """Method to Update the Partner"""
        self.ensure_one()
        if not self.field_ids:
            self.write({"state": "final"})
            return self._reopen_self()
        self._update()
        return self.open_next()

    def update_partners_automatically(self):
        for partner in self.partner_ids:
            self.partner_id = partner.id
            self.change_partner()
            self._update()
        self.write({"state": "final"})
        return self._reopen_self()

    def start_mass_update(self):
        """
        Start the process.
        """
        self.ensure_one()
        return self.open_next()

    @api.model
    def action_open_wizard(self):
        """Opens "action_partner_update_from_afip" act_window"""
        action = self.env["ir.actions.actions"]._for_xml_id(
            "l10n_ar_eynes.action_partner_update_from_afip"
        )
        action['context'] = self.env.context
        return action
