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
        self.ResPartner = self.env["res.partner"]
        self.ResDocumentType = self.env["res.document.type"]

        self.form = Form(self.ResPartner)
        self.form.name = "res.partner form tests"

    def test_document_type_and_vat_CUIT(self):
        self.form.document_type_id = self.ResDocumentType.search(
            [("name", "=", "CUIT")]
        )
        with self.assertRaises(ValidationError):
            self.form.vat = "0123456789"
            self.form.save()  # Raises "The %(doc_type)s does not seems to be correct for %(country)s"
        with self.assertRaises(ValidationError):
            self.form.vat = "012345678901"
            self.form.save()  # Raises "The %(doc_type)s does not seems to be correct for %(country)s"
        with self.assertRaises(ValidationError):
            self.form.vat = self.ResPartner.search(
                [("document_type_id", "=", "CUIT")]
            )[0].vat
            self.form.save()  # Raises "There is another partner with same VAT Information"
