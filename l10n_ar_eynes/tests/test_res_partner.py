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

    def setUp(self):
        self.form = Form(self.env["res.partner"])
        self.form.name = "res.partner form tests"

    def test_document_type_and_vat_CUIT(self):
        self.form.document_type_id = self.env["res.document.type"].search(
            [("name", "=", "CUIT")]
        )
        with self.assertRaises(ValidationError):
            self.form.vat = "0123456789"
            self.form.save()
        with self.assertRaises(ValidationError):
            records_with_cuit = self.env["res.partner"].search(
                [("document_type_id", "=", "CUIT")]
            )
            repeated_cuit = (
                records_with_cuit[0].vat if records_with_cuit else "30712306544"
            )
            self.form.vat = repeated_cuit
            self.form.save()
