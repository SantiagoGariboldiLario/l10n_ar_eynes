from odoo import api, models

FIELDS_RECURSION_LIMIT = 3


class Import(models.TransientModel):
    _inherit = 'base_import.import'

    @api.model
    def get_fields_tree(self, model, depth=FIELDS_RECURSION_LIMIT):
        res = super().get_fields_tree(model, depth=depth)
        if model == 'account.check':
            res.extend(
                [
                    {
                        'id': 'currency_rate',
                        'name': 'currency_rate',
                        'string': 'Tasa monetaria',
                        'required': True,
                        'fields': [],
                        'type': 'float',
                        'model_name': 'account.check',
                    },
                    {
                        'id': 'currency_id',
                        'name': 'currency_id',
                        'string': 'Moneda',
                        'required': True,
                        'fields': [
                            {
                                'id': 'currency_id',
                                'name': 'id',
                                'string': 'ID externo',
                                'required': True,
                                'fields': [],
                                'type': 'id',
                                'model_name': 'account.check',
                            },
                            {
                                'id': 'currency_id',
                                'name': '.id',
                                'string': 'ID de la base de datos',
                                'required': True,
                                'fields': [],
                                'type': 'id',
                                'model_name': 'account.check',
                            },
                        ],
                        'type': 'many2one',
                        'model_name': 'account.check',
                        'comodel_name': 'res.currency',
                    },
                    {
                        'id': 'company_id',
                        'name': 'company_id',
                        'string': 'Moneda',
                        'required': True,
                        'fields': [
                            {
                                'id': 'company_id',
                                'name': 'id',
                                'string': 'ID externo',
                                'required': True,
                                'fields': [],
                                'type': 'id',
                                'model_name': 'account.check',
                            },
                            {
                                'id': 'company_id',
                                'name': '.id',
                                'string': 'ID de la base de datos',
                                'required': True,
                                'fields': [],
                                'type': 'id',
                                'model_name': 'account.check',
                            },
                        ],
                        'type': 'many2one',
                        'model_name': 'account.check',
                        'comodel_name': 'res.company',
                    },
                ]
            )
        return res
