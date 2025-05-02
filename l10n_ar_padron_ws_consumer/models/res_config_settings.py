from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    check_padron_server_state = fields.Boolean(
        string="Check Server Padron State",
        config_parameter='l10n_ar_padron_ws_consumer.check_padron_server_state',
        readonly=False,
    )
