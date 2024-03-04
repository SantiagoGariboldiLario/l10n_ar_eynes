# -- coding: utf-8 --
##############################################################################
#
#   Copyright (c) 2022-2023 Eynes SRL (Eynes - Ingenieria del software)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
#
##############################################################################

import logging

from odoo.tests.common import TransactionCase, Form
from odoo.exceptions import ValidationError


_logger = logging.getLogger(__name__)


class TestResPartner(TransactionCase):

    def test_document_type_and_vat(self):
        f = Form(self.env["res.partner"])
        f.name = "Prueba de validación de CUIT"
        f.document_type_id = self.env["res.document.type"].search(
            [("name", "=", "CUIT")]
        )
        with self.assertRaises(ValidationError):
            f.vat = "0123456789"
            f.save()
