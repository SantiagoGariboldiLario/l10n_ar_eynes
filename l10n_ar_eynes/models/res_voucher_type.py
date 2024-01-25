from odoo import fields, models


class ResVoucherType(models.Model):
    _name = "res.voucher.type"
    _description = 'Voucher type'

    name = fields.Char(string="Name", required=True)
    afip_code = fields.Char(string="AFIP Code", size=3, required=True)
    voucher_model = fields.Char(string="Voucher Model")
    doc_type = fields.Selection(
        string="Document Type",
        selection=[("b", "Bill"), ("dn", "Debit Note"), ("cn", "Credit Note")],
        required=True,
    )
    denomination = fields.Selection(
        string="Denomination",
        selection=[
            ("a", "A"),
            ("b", "B"),
            ("c", "C"),
            ("e", "E"),
            ("m", "M"),
            ('oc', 'OC'),
            ('ana', 'ANA'),
        ],
        required=True,
    )
