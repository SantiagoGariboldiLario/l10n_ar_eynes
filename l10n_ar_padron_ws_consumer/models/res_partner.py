import json
import logging
from datetime import date, datetime

import requests

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..utils.helpers import get_current_period

_logger = logging.getLogger(__name__)

HEADERS = {
    "content-type": "application/json",
}


class ResPartnerPerception(models.Model):
    _inherit = "res.partner.perception"

    coeficient = fields.Float(digits=(12, 4))
    coeficient_percent = fields.Float(digits=(12, 2))
    risk = fields.Selection(
        selection=[
            ('si', 'Si'),
            ('no', 'No'),
            ('alto', 'Alto'),
        ],
        string="Risk",
    )
    is_multilateral = fields.Boolean()

    _sql_constraints = [
        (
            'perception_partner_unique_period',
            'unique(partner_id, perception_id, period)',
            _(
                'There must be only one perception of this type configured '
                'for the partner in the same period'
            ),
        )
    ]


class ResPartnerRetention(models.Model):
    _inherit = "res.partner.retention"

    is_multilateral = fields.Boolean()

    _sql_constraints = [
        (
            'retention_partner_unique_period',
            'unique(partner_id, retention_id, period)',
            _(
                'There must be only one retention of this type '
                'configured for the partner in the same period'
            ),
        )
    ]


class ResPartner(models.Model):
    _inherit = "res.partner"

    last_padron_update = fields.Date()

    @api.model
    def create(self, vals):
        res = super().create(vals)
        self.with_context(active_ids=res.ids).do_update_from_padron()
        return res

    def _get_padron_url(self):
        padron_url = self.env["ir.config_parameter"].get_param("padron_url", "")

        if not padron_url:
            raise ValidationError(
                _("Padron Error!\n")
                + _("Please configure the value 'padron_url' in the settings.")
            )
        return padron_url

    def _filter_valid_vats(self, vat_list=None):
        valid, invalid = list(), list()
        for vat in vat_list:
            try:
                if self.check_vat_ar(vat):
                    valid.append(vat)
                else:
                    invalid.append(vat)
            except BaseException:
                invalid.append(vat)
        return valid, invalid

    def _get_padron_values(
        self, vat_list, padron_url, padron_name, padron_type, from_cron
    ):
        headers = {"content-type": "application/json"}
        payload = {
            "vat": vat_list,
            "padron_name": padron_name,
            "padron_type": padron_type,
        }

        response = requests.get(
            padron_url,
            data=json.dumps(payload),
            headers=headers,
            timeout=60,
        ).json()
        if not response.get('result'):
            if from_cron:
                users_to_message = self._get_users_from_padron_group()
                self.env['res.partner'].browse(2).message_post(
                    subject=_("Problem while Updating IIBB registry"),
                    body=_(
                        "No valid values ​​have been obtained for updating the IIBB registry."
                    ),
                    partner_ids=users_to_message,
                )
            else:
                raise ValidationError(
                    _("Padron Error!\n")
                    + _("Please check if Padron WS is running")
                )
        return response["result"]

    def _get_journal_from_padron_name(self, padron_name, padron_type):
        domain = [
            ("type", "=", padron_type),
        ]
        if padron_name == "IVA":
            domain.append(("code", '=', 'PIVAE'))
        else:

            if padron_name == "ARBA":
                domain.append(
                    ("padron_state_id", '=', self.env.ref('base.state_ar_b').id)
                )
            elif padron_name == "CABA":
                domain.append(
                    ("padron_state_id", '=', self.env.ref('base.state_ar_c').id)
                )
            elif padron_name == "CORD":
                domain.append(
                    ("padron_state_id", '=', self.env.ref('base.state_ar_x').id)
                )
            elif padron_name == "JUJU":
                domain.append(
                    ("padron_state_id", '=', self.env.ref('base.state_ar_y').id)
                )
            elif padron_name == "TUCU":
                domain.append(
                    ("padron_state_id", '=', self.env.ref('base.state_ar_t').id)
                )
            elif padron_name == "MEND":
                domain.append(
                    ("padron_state_id", '=', self.env.ref('base.state_ar_m').id)
                )
            elif padron_name == "SALT":
                domain.append(
                    ("padron_state_id", '=', self.env.ref('base.state_ar_a').id)
                )
            elif padron_name == "FORM":
                domain.append(
                    ("padron_state_id", '=', self.env.ref('base.state_ar_p').id)
                )
            elif padron_name == "SANT":
                domain.append(
                    ("padron_state_id", '=', self.env.ref('base.state_ar_s').id)
                )
            elif padron_name == "ENTR":
                domain.append(
                    ("padron_state_id", '=', self.env.ref('base.state_ar_e').id)
                )

            if padron_type == 'perceptions':
                domain.append(("code", 'like', 'PIE_'))
            elif padron_type == 'retentions':
                domain.append(("code", 'like', 'RIE_'))

        journal_id = self.env["account.journal"].search(domain)
        return journal_id

    def _build_date_from_integer(self, month):
        today = date.today()
        if month == 0:  # To use with yearly taxes
            padron_date = today.replace(day=1).replace(month=1)
        elif month <= today.month + 1:
            padron_date = today.replace(day=1).replace(month=month)
        else:
            padron_date = (
                today.replace(day=1)
                .replace(month=month + 1)
                .replace(year=today.year - 1)
            )
        return padron_date

    def _get_iibb_situation(self, perception):
        if perception.get("P") == 'SANT' and perception.get("L"):
            iibb_situation = self.env.ref('l10n_ar_eynes.iibb_situation_local')
        elif perception.get("ML"):
            iibb_situation = self.env.ref(
                'l10n_ar_eynes.iibb_situation_multilateral'
            )
        else:
            iibb_situation = self.env.ref('l10n_ar_eynes.iibb_situation_local')
        return iibb_situation.id

    def _update_partner_perceptions(self, partner, perceptions):
        for perception in perceptions:
            journal_id = self._get_journal_from_padron_name(
                perception["P"], 'perceptions'
            )
            if journal_id:
                # if padron available and active, then create/update perception
                period = self._build_date_from_integer(int(perception["M"]))
                iibb_situation = self._get_iibb_situation(perception)
                res_partner_perception = self.env[
                    "res.partner.perception"
                ].search(
                    [
                        ("perception_id", "=", journal_id.tax_id.id),
                        ("partner_id", "=", partner.id),
                        ("period", "=", period),
                        ("from_padron", "=", True),
                    ]
                )
                percent = perception.get("V")
                excluded_percent = perception.get("E")
                risk = perception.get("R", False)
                if risk:
                    risk = risk.lower()
                if percent:
                    percent = str(percent).replace(",", ".")
                if res_partner_perception:
                    res_partner_perception.write(
                        {
                            "percent": percent,
                            "sit_iibb": iibb_situation,
                            "risk": risk,
                            "excluded_percent": excluded_percent,
                            "from_padron": True,
                        }
                    )
                else:
                    res_partner_perception.create(
                        {
                            "perception_id": journal_id.tax_id.id,
                            "partner_id": partner.id,
                            "percent": percent,
                            "risk": risk,
                            "sit_iibb": iibb_situation,
                            "period": period,
                            "from_padron": True,
                            "excluded_percent": excluded_percent,
                        }
                    )
            _logger.debug(
                f'Create Perception {journal_id.name} for partner {partner.name}'
            )

    def _update_partner_retentions(self, partner, retentions):
        for retention in retentions:
            journal_id = self._get_journal_from_padron_name(
                retention["P"], 'retentions'
            )
            if journal_id:
                # if padron available and active, then create/update retentions
                period = self._build_date_from_integer(int(retention["M"]))
                iibb_situation = self._get_iibb_situation(retention)
                res_partner_retention = self.env[
                    "res.partner.retention"
                ].search(
                    [
                        ("retention_id", "=", journal_id.tax_id.id),
                        ("partner_id", "=", partner.id),
                        ("period", "=", period),
                        ("from_padron", "=", True),
                    ]
                )
                percent = retention.get("V")
                if percent:
                    percent = str(percent).replace(",", ".")
                if res_partner_retention:
                    res_partner_retention.write(
                        {
                            "percent": percent,
                            "sit_iibb": iibb_situation,
                        }
                    )
                else:
                    res_partner_retention.create(
                        {
                            "retention_id": journal_id.tax_id.id,
                            "partner_id": partner.id,
                            "percent": percent,
                            "sit_iibb": iibb_situation,
                            "period": period,
                            "from_padron": True,
                        }
                    )
            _logger.debug(
                f'Create Retention {journal_id.name} for partner {partner.name}'
            )

    def _update_partner_coeficients(self, partner, coeficients):
        for coeficient in coeficients:

            journal_id = self._get_journal_from_padron_name(
                coeficient["P"], 'perceptions'
            )
            if journal_id:
                period = self._build_date_from_integer(int(coeficient["M"]))
                res_partner_perception = self.env[
                    "res.partner.perception"
                ].search(
                    [
                        ("perception_id", "=", journal_id.tax_id.id),
                        ("partner_id", "=", partner.id),
                        ("period", "=", period),
                        ("from_padron", "=", True),
                    ]
                )
                percent = coeficient.get("V")
                coeficient = coeficient.get("C")
                if percent:
                    percent = str(percent).replace(",", ".")

                if coeficient:
                    coeficient = str(coeficient).replace(",", ".")
                    data = {
                        "coeficient": coeficient,
                        "coeficient_percent": percent,
                        "from_padron": True,
                    }
                if coeficient == 'E':
                    data["coeficient"] = 0
                    data["coeficient_percent"] = 0
                    data["excluded_percent"] = 1

                if res_partner_perception:
                    res_partner_perception.write(data)
                else:
                    data["perception_id"] = journal_id.tax_id.id
                    data["partner_id"] = partner.id
                    data["percent"] = 0
                    data["period"] = period
                    res_partner_perception.create(data)
            _logger.debug(
                f'Write Coeficient into {journal_id.name} for partner {partner.name}'
            )

    def _update_partner_ivas(self, partner, ivas):
        for iva in ivas:
            journal_id = self._get_journal_from_padron_name(
                iva["P"], 'perceptions'
            )
            if journal_id:
                period = self._build_date_from_integer(int(iva["M"]))
                res_partner_perception = self.env[
                    "res.partner.perception"
                ].search(
                    [
                        ("perception_id", "=", journal_id.tax_id.id),
                        ("partner_id", "=", partner.id),
                        ("period", "=", period),
                        ("from_padron", "=", True),
                    ]
                )
                excluded_percent = iva.get("V")
                datetime_format = '%d/%m/%Y'
                ex_date_from = datetime.strptime(iva.get("D"), datetime_format)
                ex_date_to = datetime.strptime(iva.get("H"), datetime_format)
                if res_partner_perception:
                    res_partner_perception.write(
                        {
                            "ex_date_from": ex_date_from,
                            "ex_date_to": ex_date_to,
                            "excluded_percent": excluded_percent,
                        }
                    )
                else:
                    res_partner_perception.create(
                        {
                            "perception_id": journal_id.tax_id.id,
                            "partner_id": partner.id,
                            "percent": 0,
                            "ex_date_from": ex_date_from,
                            "ex_date_to": ex_date_to,
                            "excluded_percent": excluded_percent,
                            "period": period,
                            "from_padron": True,
                        }
                    )
            _logger.debug(
                f'Write iva into {journal_id.name} for partner {partner.name}'
            )

    def _get_users_from_padron_group(self):
        group_xml_id = (
            'l10n_ar_padron_ws_consumer.group_receive_padron_notifications'
        )
        return self.env.ref(group_xml_id).users.mapped('partner_id').ids

    def _cleanup_old_padron_values(self):
        _logger.debug('Deleting OLD padron')

        query = """
            DELETE FROM res_partner_perception WHERE
                period <= date_trunc('month', now()) - interval '6 months';
            DELETE FROM res_partner_retention WHERE
                period <= date_trunc('month', now()) - interval '6 months';
        """
        self.env.cr.execute(query)

    def _validate_partners_vat(self, partners, from_cron):
        message = ""
        vat_list = [partner.vat for partner in partners]
        valid, invalid = self._filter_valid_vats(vat_list)
        if not valid and not from_cron:
            raise ValidationError(
                _("Padron Error!\n") + _("No partner with valid VAT to check.")
            )
        if not valid:
            message = "\nNo existen partners con CUIT Válido para verificar"

        if invalid and from_cron:
            message = (
                _(
                    'There are partners with the following CUIT %s that are invalid.\n'
                    + 'Correct them so that there are no errors with the IIBB update'
                )
                % invalid
            )
        if message:
            users_to_message = self._get_users_from_padron_group()
            self.env['res.partner'].browse(2).message_post(
                subject=_("Possible Problems while Updating IIBB Registers"),
                body=message,
                partner_ids=users_to_message,
            )
        return valid

    def do_update_from_padron(
        self,
        padron_name=None,
        padron_type=None,
        from_cron=None,
        check_server_state=False,
    ):
        if padron_name is None:
            padron_name = []

        if padron_type is None:
            padron_type = []

        padron_url = self._get_padron_url()
        payload = {
            "status": True,
        }

        check_padron_server_state = (
            self.env['ir.config_parameter']
            .sudo()
            .get_param('l10n_ar_padron_ws_consumer.check_padron_server_state')
        )

        if check_server_state or check_padron_server_state:
            try:
                _logger.info('Checking Padron URL State')
                response = requests.head(
                    padron_url,
                    headers=HEADERS,
                    data=json.dumps(payload),
                    timeout=60,
                )
                if response.status_code != 200:
                    raise ValidationError(
                        _("Padron Error!\n") + _("Error in response CODE.")
                    )
            except requests.RequestException as err:
                raise ValidationError(
                    _("Padron Error!\n") + _("Padron server is not reachable.")
                ) from err

        self._cleanup_old_padron_values()

        _logger.info('Update Padron')

        valid_document_types = [
            self.env.ref("l10n_ar_eynes.document_cuit").id,
            self.env.ref("l10n_ar_eynes.document_cuit_country").id,
        ]
        padron_url = self._get_padron_url()
        current_period = get_current_period()
        domain = [
            ('document_type_id', 'in', valid_document_types),
            ('parent_id', '=', False),
            ('vat', '!=', False),
        ]
        partner_ids = self.env.context.get('active_ids', [])
        if partner_ids:
            domain_append = [('id', 'in', partner_ids)]
        else:
            domain_append = [
                '|',
                ('last_padron_update', '=', False),
                ('last_padron_update', '<', current_period),
            ]
        domain = domain + domain_append
        res_partner_obj = self.env["res.partner"]
        partners = res_partner_obj.search(domain)
        _logger.info('Getting Padron Information')
        if partners:
            valid_vat = self._validate_partners_vat(partners, from_cron)

            updates = set()
            response = self._get_padron_values(
                valid_vat, padron_url, padron_name, padron_type, from_cron
            )
            _logger.info('Padron Information Fetched')
            for vat, partner_values in response.items():
                try:
                    perceptions = [
                        d
                        for d in partner_values
                        if d["T"] == "P" and d["P"] != "SALT"
                    ]
                    retentions = [d for d in partner_values if d["T"] == "R"]
                    coeficients = [
                        d
                        for d in partner_values
                        if d["T"] == "C" or (d["T"] == "P" and d["P"] == "SALT")
                    ]
                    ivas = [d for d in partner_values if d["T"] == "I"]

                    partner_id = res_partner_obj.search(
                        [
                            ("vat", "=", vat),
                            ('parent_id', '=', False),
                        ],
                        limit=1,
                    )
                    self._update_partner_perceptions(partner_id, perceptions)
                    self._update_partner_retentions(partner_id, retentions)
                    self._update_partner_coeficients(partner_id, coeficients)
                    self._update_partner_ivas(partner_id, ivas)
                    partner_id.write(
                        {
                            "last_padron_update": current_period,
                        }
                    )
                    total_updates = perceptions + retentions + coeficients
                    new_values = {
                        value
                        for value in [
                            value["P"] + " - " + value["M"]
                            for value in total_updates
                        ]
                    }
                    updates.update(new_values)
                except Exception:
                    _logger.info(_("No partners to check. All updated."))

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'type': 'info',
                    'sticky': True,
                    'message': (
                        "Se actualizaron los siguientes Padrones: "
                        + " | ".join([value for value in updates])
                    ),
                },
            }
