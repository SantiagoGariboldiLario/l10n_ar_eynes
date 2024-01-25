from . import models
from . import wizard
from . import controllers
from . import utils
from . import wsfetools
from . import report
from odoo import api, SUPERUSER_ID


def _install_language(cr, registry):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['base.language.install'].create(
        {'lang': 'es_AR', 'overwrite': True}
    ).lang_install()


def _switch_users_language(cr, registry):
    env = api.Environment(cr, SUPERUSER_ID, {})
    user = env['res.users'].search([])
    user.write({'lang': 'es_AR'})


def _switch_partners_language(cr, registry):
    env = api.Environment(cr, SUPERUSER_ID, {})
    partners = env['res.partner'].search([])
    partners.write({'lang': 'es_AR'})


def post_init_hook(cr, registry):
    _install_language(cr, registry)
    _switch_users_language(cr, registry)
    _switch_partners_language(cr, registry)
