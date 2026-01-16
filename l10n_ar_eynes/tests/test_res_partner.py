##############################################################################
#
#   Copyright (c) 2022-2023 Eynes SRL (Eynes - Ingenieria del software)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
#
##############################################################################

import logging
import unittest

from odoo.exceptions import ValidationError
from odoo.tests.common import Form, TransactionCase

_logger = logging.getLogger(__name__)


class TestResPartnerForm(TransactionCase):

    def setUp(self):
        super().setUp()
        self.ResPartner = self.env["res.partner"]
        self.company_types = ("person", "company")
        self.form = Form(self.ResPartner)
        self.form.name = "res.partner form tests"


class TestResPartnerDocumentTypeAndVat(TestResPartnerForm):

    def setUp(self):
        super().setUp()
        self.ResDocumentType = self.env["res.document.type"]

    def test_CUIT(self):
        self.form.document_type_id = self.ResDocumentType.search(
            [("name", "=", "CUIT")]
        )
        for company_type in self.company_types:
            with self.subTest(company_type):
                self.form.company_type = company_type
                self._is_valid_CUIT()
            with self.subTest(company_type):
                self.form.company_type = company_type
                self._is_reapeated_CUIT()

    def test_DNI(self):
        self.form.document_type_id = self.ResDocumentType.search(
            [("name", "=", "DNI")]
        )
        for company_type in self.company_types:
            with self.subTest(company_type):
                self.form.company_type = company_type
                self._is_valid_DNI()
            with self.subTest(company_type):
                self.form.company_type = company_type
                self._is_repeated_DNI()

    def _is_valid_CUIT(self):
        with self.assertRaises(
            ValidationError,
            msg="The %(doc_type)s does not seems to be correct for %(country)s",
        ):
            self.form.vat = "0123456789"
            self.form.save()
        with self.assertRaises(
            ValidationError,
            msg="The %(doc_type)s does not seems to be correct for %(country)s",
        ):
            self.form.vat = "012345678901"
            self.form.save()
        with self.assertRaises(
            ValidationError,
            msg="The %(doc_type)s does not seems to be correct for %(country)s",
        ):
            self.form.vat = "30712306545"
            self.form.save()

    def _is_reapeated_CUIT(self):
        partners_w_CUIT = self.ResPartner.search(
            [("document_type_id", "=", "CUIT")]
        )
        CUIT_on_db = (
            partners_w_CUIT[0].vat if partners_w_CUIT else "30712306544"
        )

        if not partners_w_CUIT:
            self.form.vat = CUIT_on_db
            self.form.save()

        with self.assertRaises(
            ValidationError,
            msg="There is another partner with same VAT Information",
        ):
            self.form.vat = CUIT_on_db
            self.form.save()

    def _is_valid_DNI(self):
        with self.assertRaises(ValidationError, msg="DNI is too short"):
            self.form.vat = "123456"
            self.form.save()
        with self.assertRaises(ValidationError, msg="DNI is too long"):
            self.form.vat = "123456789"
            self.form.save()

    @unittest.skip("Generally we don't care if DNIs are repeated")
    def _is_repeated_DNI(self):
        partners_w_DNI = self.ResPartner.search(
            [("document_type_id", "=", "DNI")]
        )
        DNI_on_db = partners_w_DNI[0].vat if partners_w_DNI else "40123456"

        if not partners_w_DNI:
            self.form.vat = DNI_on_db
            self.form.save()

        with self.assertRaises(ValidationError, msg="DNI is already in DB"):
            self.form.vat = DNI_on_db
            self.form.save()
