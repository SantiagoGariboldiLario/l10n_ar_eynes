from . import models
from . import wizard
from . import controllers
from . import utils
from . import wsfetools
from . import report
from odoo import api, SUPERUSER_ID


def _install_language(env):
    es_ar = env['res.lang'].search([('code', '=', 'es_AR')])
    # TODO: aca al instalar es_ar es vacío, no lo encuentra
    env["base.language.install"].create(
        {
            'overwrite': True,
            'lang_ids': [(6, 0, [es_ar.id])],
        }
    ).lang_install()


def _switch_users_language(env):
    user = env['res.users'].search([])
    user.write({'lang': 'es_AR'})


def _switch_partners_language(env):
    partners = env['res.partner'].search([])
    partners.write({'lang': 'es_AR'})


def post_init_hook(env):
    _install_language(env)
    _switch_users_language(env)
    _switch_partners_language(env)
