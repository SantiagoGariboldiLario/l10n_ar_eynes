##############################################################################
#   Copyright (c) 2019 Eynes/E-MIPS (www.eynes.com.ar)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
##############################################################################

import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class ReportExporter(models.Model):
    _name = 'report.exporter'
    _description = 'Report Exporter'

    def _default_groups(self):
        return self.env.ref(
            'account.group_account_manager', raise_if_not_found=False
        )

    name = fields.Char(required=True)
    codename = fields.Char(required=True, readonly=True)
    group_ids = fields.Many2many(
        'res.groups', string='Groups', default=_default_groups
    )
    # related_ui_ids = fields.Many2many('ir.model.data')

    # def _register_hook(self):
    #     res = super()._register_hook()
    #     records = self.search([])
    #     _logger.info("Generating Exporter Menus")
    #     for rec in records:
    #         rec.refresh_ui_stuff()
    #     return res

    # def refresh_ui_stuff(self):
    #     """
    #     Prepares the menues and actions.
    #     """
    #     if self._context.get('no_ui_update'):
    #         return
    #     self.ensure_one()
    #     basename = 'base_report_exporter'

    #     # Actw wizard of exporter
    #     exporter_act_window_id = '%s.action_rfg_%s_exporter' % (
    #         basename, self.codename)
    #     ctx_in_act = {
    #         'default_exporter_id': self.id,
    #     }
    #     exporter_aw_values = {
    #         'model': 'ir.actions.act_window',
    #         'id': exporter_act_window_id,
    #         'name': self.name + _(' Exporter'),
    #         'res_model': 'report.files.generator',
    #         'type': 'ir.actions.act_window',
    #         'view_mode': 'form',
    #         'target': 'new',
    #         'context': ctx_in_act.__str__(),
    #     }
    #     self.create_or_update(exporter_aw_values)

    #     # Main menu for this exporter
    #     main_menu_id = '%s.menu_rfg_%s_main' % (basename, self.codename)
    #     main_menu_values = {
    #         'model': 'ir.ui.menu',
    #         'id': main_menu_id,
    #         'name': self.name,
    #         'parent_id': 'l10n_ar_eynes.menu_parent_exporters',
    #     }
    #     self.create_or_update(main_menu_values)

    #     # Menu of wizard & associate it
    #     exporter_menu_id = '%s.menu_rfg_%s_exporter' % (
    #         basename, self.codename)
    #     generator_menu_values = {
    #         'model': 'ir.ui.menu',
    #         'id': exporter_menu_id,
    #         'name': self.name + _(' Exporter'),
    #         'parent_id': '%s' % main_menu_id,
    #         'action': exporter_act_window_id,
    #     }
    #     self.create_or_update(generator_menu_values)

    #     # Actw for viewing the reports
    #     view_act_window_id = '%s.action_rfg_%s_view_reports' % (
    #         basename, self.codename)
    #     ctx_in_act = {}
    #     view_aw_values = {
    #         'model': 'ir.actions.act_window',
    #         'id': view_act_window_id,
    #         'name': self.name + _(' Reports'),
    #         'res_model': 'report.files',
    #         'type': 'ir.actions.act_window',
    #         'view_mode': 'tree,form',
    #         'domain': [('exporter_id', '=', self.id)],
    #         'context': ctx_in_act.__str__(),
    #     }
    #     self.create_or_update(view_aw_values)

    #     # Menu for viewing the reports & associate it
    #     exporter_menu_id = '%s.menu_rfg_%s_reports' % (basename, self.codename)
    #     generator_menu_values = {
    #         'model': 'ir.ui.menu',
    #         'id': exporter_menu_id,
    #         'name': self.name + _(' Reports'),
    #         'parent_id': '%s' % main_menu_id,
    #         'action': view_act_window_id,
    #     }
    #     self.create_or_update(generator_menu_values)

    # def create_or_update(self, values):
    #     """{'id': 'fq extid', 'model': 'ir.ui.view'}"""
    #     assert 'model' in values, 'model must be in values'
    #     assert 'id' in values, 'external_id is required'
    #     external_id = values.pop('id')
    #     model = values.pop('model')
    #     # Search the object
    #     obj = self.env.ref(external_id, raise_if_not_found=False)
    #     if 'parent_id' in values:
    #         values['parent_id'] = self.env.ref(values.get('parent_id')).id
    #         # ^-- get the object based on the string
    #     if 'action' in values:
    #         live_obj = self.env.ref(values.get('action'))
    #         ref_text = '%s,%s' % (live_obj._name, live_obj.id)
    #         values['action'] = ref_text
    #         # ^-- get the object based on the string
    #     if obj:
    #         obj.write(values)
    #     else:
    #         obj_model = self.env[model]
    #         obj = obj_model.create(values)
    #         # Generate imd data
    #         imd_obj = self.env['ir.model.data']
    #         module, name = external_id.split('.')
    #         imd_rec = imd_obj.create({
    #             'model': obj_model._name,
    #             'name': name,
    #             'module': module,
    #             'res_id': obj.id,
    #         })
    #         self.with_context(no_ui_update=True).write({
    #             'related_ui_ids': [(4, imd_rec.id, 0)],
    #         })

    # def unlink(self):
    #     tounlink_also = self.related_ui_ids
    #     res = super().unlink()
    #     _logger.warning('Unlinking %s' % tounlink_also)
    #     for imd in tounlink_also:
    #         model, oid = imd.model, imd.res_id
    #         self.env[model].browse(oid).unlink()
    #     return res
