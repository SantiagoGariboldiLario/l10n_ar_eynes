from odoo import fields, models, api


class AccreditCheckWizard(models.Model):
    _name = 'accredit.check.wizard'
    _description = 'Select several checks which are Waiting Accreditation so you can accredit them'

    @api.model
    def get_default_checks(self):
        """ Get active checks"""
        check_ids = self.env.context.get("active_ids", [])
        return [(6, False, check_ids)]

    issued_checks = fields.Many2many(
        comodel_name='account.check',
        relation='wiz_accredit_check_rel',
        colum1='wiz_id',
        colum2='check_id',
        default=get_default_checks,
    )

    def button_accredit_checks(self):
        """ button that run accredit checks action"""
        return self.issued_checks.accredit_checks()
