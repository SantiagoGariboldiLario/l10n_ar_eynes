import logging
import re

import requests

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = "res.company"

    apartment = fields.Char(
        string="Apartment",
        related="partner_id.apartment",
        store=True,
    )
    apportionable_vat = fields.Boolean()
    cbu = fields.Char(
        string='CBU para Facturas A',
        size=32,
        required=False,
        copy=False,
        help='CBU informado para Facturas A debe estar previamente informado en ARCA.',
    )
    cot_pass = fields.Char(string="COT Password")
    cot_url = fields.Char(string="COT URL")
    cot_user = fields.Char(string="COT User (NIF)")
    door = fields.Char(
        string="Door",
        related="partner_id.door",
        size=3,
        store=True,
    )
    fcred_cbu_emitter = fields.Char(string='CBU (FCE)')
    fcred_is_fce_emitter = fields.Boolean(string='FCE Emitter?', default=False)
    fcred_minimum_amount = fields.Float(
        string='Monto Minimo (FCE)',
        default=195698,
    )
    fcred_pos_ar_id = fields.Many2one(
        'account.journal',
        string='FCE Pos',
        domain="[('fcred_is_fce_emitter', '=', True)]",
    )
    fcred_transfer = fields.Char(string='SCA/ADC (FCE)?', default='SCA')
    floor = fields.Char(
        string="Floor",
        related="partner_id.floor",
        size=3,
        store=True,
    )
    group_check_cot = fields.Boolean(
        string="Enable Web Service",
        implied_group="l10n_ar_eynes.group_check_cot",
    )
    num = fields.Char(
        string="Number",
        related="partner_id.num",
        size=5,
        store=True,
    )


class AfipBigCompany(models.Model):
    _name = 'afip.big.company'
    _description = "CUIT of companies categorized as 'Big Companies' by AFIP"

    cuit = fields.Char(string='CUIT')

    @api.model
    def get_from_afip(self):
        """
        Retrieves all the cuits from AFIP endpoint
        """
        REQ = requests.post(
            'https://servicioscf.afip.gob.ar/FCEServicioConsulta/api/fceconsulta.aspx/getGrandesEmpresas',  # noqa
            timeout=300,
        )
        raw_response = REQ.text
        list_of_cuit = re.findall('Cuit..([0-9]*)', raw_response)
        return list_of_cuit

    @api.model
    def do_update(self):
        """
        Updates the table of big companies
        """
        ss = self.sudo()
        ss.search([]).unlink()
        big_companies = self.get_from_afip()
        for cuit in big_companies:
            ss.create({'cuit': cuit})
        _logger.info(
            '[afip.big.company] has retrieved the '
            'following companies from afip and updated the local table'
        )
        _logger.info(big_companies)
