##############################################################################
#   Copyright (c) 2019 Eynes/E-MIPS (www.eynes.com.ar)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
##############################################################################

import binascii
import json
import logging

from odoo import _, api, exceptions, fields, models

_logger = logging.getLogger(__name__)


class ReportFilesGenerator(models.Model):
    _name = 'report.files.generator'

    exporter_id = fields.Many2one('report.exporter', 'Exporter', required=True)
    exporter_codename = fields.Char(
        related='exporter_id.codename', readonly=True
    )
    date_start = fields.Date()
    date_stop = fields.Date()
    company_id = fields.Many2one('res.company', string='Company')
    company_id_domain = fields.Char(
        default=lambda self: self._default_company_ids()
    )

    @api.model
    def _default_company_ids(self):
        return json.dumps(
            [('id', 'in', self.env.context.get('allowed_company_ids', []))]
        )

    def get_dates(self):
        return (self.date_start, self.date_stop)

    def do_store(self, state, errors, files):
        report_file_model = self.env['report.files']
        report_file_id = self.env.context.get('report_file_id')
        report_file = report_file_id and report_file_model.browse(
            report_file_id
        )

        date_start, date_stop = self.get_dates()
        name = '%s [%s -> %s]' % (self.exporter_id.name, date_start, date_stop)
        _read = self.read()[0]
        values = self._convert_to_write(_read)
        values.update(
            {
                'name': name,
                'state': 'generated' if state else 'error',
            }
        )
        error_values = []
        for err in errors:
            model = err['resource']._name
            oid = err['resource'].id
            resource_str = '%s,%s' % (model, oid)
            error_values.append(
                (
                    0,
                    0,
                    {
                        'resource_ref': resource_str,
                        'error': err['error'],
                        'type': err.get('type', 'error'),
                    },
                )
            )
        values['error_ids'] = error_values
        if isinstance(report_file, models.BaseModel):
            report_file.attachment_ids.unlink()
            report_file.error_ids.unlink()
            report_file.write(values)
            new_file = report_file
        else:
            new_file = report_file_model.create(values)
        if state:
            for ffile in files:
                f = ffile.get('data')
                try:
                    f.seek(0)
                    data = f.read()
                except Exception:
                    try:
                        data = ("\r\n").join(f)
                    except Exception:
                        data = f
                if isinstance(data, str):
                    data = data.encode('ascii', 'replace')
                encoded_data = binascii.b2a_base64(data)
                data_attach = {
                    'name': ffile.get('name'),
                    'store_fname': ffile.get('name'),
                    'datas': encoded_data,
                    'res_id': new_file.id,
                    'res_model': 'report.files',
                    'report_file_id': new_file.id,
                }
                self.env['ir.attachment'].create(data_attach)
        form_view = self.env.ref('l10n_ar_eynes.report_files_view_form')
        tree_view = self.env.ref('l10n_ar_eynes.report_files_view_tree')
        views = [(form_view.id, 'form'), (tree_view.id, 'tree')]
        return {
            'name': _('Report'),
            'type': 'ir.actions.act_window',
            'res_model': 'report.files',
            'view_mode': 'form',
            'views': views,
            'res_id': new_file.id,
        }

    def postprocess(self, ddict):
        """
        ddict = {
            'state': True|False,
            'errors': [{'resource': recordset, 'error': 'error'}]
            'files': [{'name': 'filename', 'data': IO Buffer}]
        }
        """
        assert isinstance(ddict, dict), 'ddict must be a diktionary'
        state = ddict.get('state')
        errors = ddict.get('errors', [])
        files = ddict.get('files')
        assert isinstance(state, bool), 'state must be boolean'
        assert isinstance(errors, list), 'errors must be a list'
        assert isinstance(files, list), 'files must be a list'
        if state is False:
            assert len(errors) >= 1, (
                'Expected at least one ' + 'error if no success'
            )
        else:
            assert len(files) >= 1, 'Expected at least one file if no errors'
        res = self.do_store(state, errors, files)
        return res

    def _control_error(self, e):
        _logger.exception(
            'Unable to export %s:\n%s' % (self.exporter_codename, str(e))
        )
        raise exceptions.ValidationError(
            _('Unable to export. More info in logs.\n' + 'Error was:\n%s')
            % str(e)
        )

    def do_generate(self):
        """
        Calls _do_<exporter_id.codename>
        """
        fname = '_do_%s' % self.exporter_codename
        if not hasattr(self, fname):
            raise exceptions.ValidationError(
                _('Exporter Failure.\n[undefined %s]') % fname
            )
        # Call function with proper parameter
        fn = getattr(self, fname)
        try:
            res = fn()
        except Exception as e:
            self._control_error(e)

        if not res:
            raise exceptions.ValidationError(
                _("Sorry, there is nothing to export 😢")
            )
        try:
            end_res = self.postprocess(res)
        except Exception as e:
            self._control_error(e)
        else:
            return end_res


class ReportFiles(models.Model):
    _inherit = 'report.files.generator'
    _name = 'report.files'
    _description = 'Exported Files'

    STATES = [
        ('error', 'Error'),
        ('generated', 'Generated'),
        ('declared', 'Declared'),
    ]

    name = fields.Char(required=True)

    state = fields.Selection(selection=STATES, required=True)
    error_ids = fields.One2many(
        'report.files.error', 'file_id', string='Errors'
    )
    attachment_ids = fields.One2many(
        'ir.attachment', inverse_name='report_file_id', string="Attachments"
    )

    def to_declared(self):
        self.write({'state': 'declared'})

    def to_generated(self):
        self.write({'state': 'generated'})

    def regenerate(self):
        for rec in self:
            rec.with_context(report_file_id=rec.id).do_generate()
        return True

    def unlink(self):
        # Remove related records from error_ids
        for rec in self:
            rec.error_ids.unlink()
        return super(ReportFiles, self).unlink()


class ReportFilesError(models.Model):
    _name = 'report.files.error'
    _description = 'Errors for an exportat'

    resource_ref = fields.Char(required=True)
    resource_name = fields.Char(compute='_compute_resource_name')
    error = fields.Text(required=True)
    file_id = fields.Many2one('report.files', required=True)
    type = fields.Selection(
        [
            ('error', 'Error'),
            ('warning', 'Warning'),
        ],
        string="Type",
        default='error',
    )

    def goto(self):
        model, oid = self.resource_ref.split(',')
        res = {
            'name': self.error,
            'type': 'ir.actions.act_window',
            'res_model': model,
            'view_mode': 'form',
            'res_id': int(oid),
        }
        return res

    def _compute_resource_name(self):
        for error in self:
            model, oid_str = error.resource_ref.split(',')
            oid = int(oid_str)
            obj = self.env[model].browse(oid)
            name = obj.display_name
            error.resource_name = '[%s] %s' % (model, name)
