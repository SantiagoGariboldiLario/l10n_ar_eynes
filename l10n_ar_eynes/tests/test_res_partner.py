# -- coding: utf-8 --
##############################################################################
#
#   Copyright (c) 2022-2023 Eynes SRL (Eynes - Ingenieria del software)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
#
##############################################################################

import logging

from odoo.tests.common import TransactionCase

_logger = logging.getLogger(__name__)


class TestResPartner(TransactionCase):

    def test_document_type_and_vat(self):
        with Form(self.env["res.partner"]) as f:
            import wdb

            wdb.set_trace()
            pass
