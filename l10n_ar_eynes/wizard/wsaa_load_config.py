##############################################################################
#   Copyright (c) 2023 Eynes/E-MIPS (www.eynes.com.ar)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
##############################################################################

import base64
from tempfile import TemporaryFile

from odoo import _, fields, models
from odoo.exceptions import ValidationError


class WSAALoadConfig(models.TransientModel):
    _name = 'wsaa.load.config'
    _description = 'Load configuration for WSAA'

    def read_file(self, filename=False, filedata=False, ext=False):
        if not filename or not filedata or not ext:
            raise Exception('Wrong call parameters to `load_file` method')
        if not (filedata):
            raise ValidationError(_('Error ! You must enter a File'))
        pieces = filename.split('.')
        if len(pieces) < 2 or pieces[-1] != ext:
            err = _('Error!\nThe Filename should end in ".%s"') % ext
            raise ValidationError(err)
        fileobj = TemporaryFile('w+')
        fileobj.write(base64.b64decode(filedata).decode('utf-8'))
        fileobj.seek(0)
        lines = fileobj.read()
        fileobj.close()
        return lines

    def load_cert(self):
        form_id = self.env.context.get('active_ids', False)
        if not form_id or len(form_id) != 1:
            raise Exception('Wizard method call without `active_ids` in ctx')
        wiz = self
        certificate = wiz.certificate
        cert_name = wiz.cert_name
        filedata = self.read_file(cert_name, certificate, 'crt')
        model = self.env[self.env.context.get('active_model', 'wsaa.config')]
        obj = model.browse(form_id)
        field = self.env.context.get('field', 'certificate')
        write_vals = {
            field: filedata,
        }
        obj.write(write_vals)

    def load_key(self):
        form_id = self.env.context.get('active_ids', False)
        if not form_id or len(form_id) != 1:
            raise Exception('Wizard method call without `active_ids` in ctx')
        wiz = self
        key = wiz.key
        key_name = wiz.key_name
        filedata = self.read_file(key_name, key, 'key')
        model = self.env[self.env.context.get('active_model', 'wsaa.config')]
        obj = model.browse(form_id)
        field = self.env.context.get('field', 'key')
        write_vals = {
            field: filedata,
        }
        obj.write(write_vals)

    certificate = fields.Binary('Certificate of Approval', help="You certificate (.crt)")
    cert_name = fields.Char('Cert FileName')
    key = fields.Binary('Private Key', help="You Privary Key Here")
    key_name = fields.Char('Key FileName')
