from odoo import models, fields


class ResParterBank(models.Model):
    _inherit = 'res.partner.bank'

    def name_get(self):
        result = []
        for rpb in self:
            name = []
            if rpb.bank_id:
                name.append("[%s]" % rpb.bank_id.name_get()[0][1])
            name.append(rpb.acc_number)
            result.append((rpb.id, " ".join(name)))
        return result

    account_id = fields.Many2one(
        comodel_name='account.account',
        string='Account'
    )
