##############################################################################
#   Copyright (c) 2023 Eynes/E-MIPS (www.eynes.com.ar)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
##############################################################################

import json

from werkzeug.exceptions import InternalServerError

from odoo import http
from odoo.http import content_disposition, request, route, serialize_exception
from odoo.tools.misc import html_escape

# from odoo.addons.web.controllers import main as report


class MyController(http.Controller):
    @route('/l10n-version', auth='public')
    def handler(self):
        version = (
            request.env['ir.module.module']
            .sudo()
            .search([('name', '=', 'l10n_ar_eynes')])
            .installed_version
        )
        return version


class DownloadController(http.Controller):
    @http.route('/web/binary/download_document', type='http', auth="public")
    def download_document(self, model, field, _id, filename=None, **kw):
        """Download link for string fields
        :param str model: name of the model to fetch the binary from
        :param str field: binary field
        :param str id: id of the record from which to fetch the binary
        :param str filename: field holding the file's name, if any
        :returns: :class:`werkzeug.wrappers.Response`
        """
        Model = request.env[model]
        fields = [field]
        Obj = Model.browse(int(_id))
        res = Obj.read(fields)[0]
        filecontent = res.get(field)
        if not filecontent:
            return request.not_found()
        if not filename:
            filename = '%s_%s' % (model.replace('.', '_'), _id)

        try:
            response = request.make_response(
                filecontent,
                [
                    ('Content-Type', 'text/plain'),
                    ('Content-Disposition', content_disposition(filename)),
                ],
            )
            return response
        except Exception as e:
            se = serialize_exception(e)
            error = {'code': 200, 'message': 'Odoo Server Error', 'data': se}
            res = request.make_response(html_escape(json.dumps(error)))
            raise InternalServerError(response=res) from e
