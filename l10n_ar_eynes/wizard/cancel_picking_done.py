# -*- encoding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (c) 2015 E-MIPS (http://www.e-mips.com.ar)
#    Copyright (c) 2018 Eynes Ingenieria del software (http://www.eynes.com.ar)
#    Copyright (c) 2018 Aconcagua Team (http://www.proyectoaconcagua.com.ar)
#    All Rights Reserved. See AUTHORS for details.
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from odoo import fields, models, api, _
from odoo.exceptions import Warning

class CancelPickingDone(models.TransientModel):
    _name = 'cancel.picking.done'

    reason = fields.Text(string='Reason of cancellation')
    next_action = fields.Selection([('renumerate', 'Cancel & Create draft'), ('cancel', 'Cancel only')], string='Next Action', required=True)

    def create_returns(self):
        
        pick_obj = self.env['stock.picking']
        move_obj = self.env['stock.move']

        # Obtenemos el picking
        new_picks = []
        for pick in pick_obj.search([('id','=',self._context.get('active_id', False))]):
            
            # Renumerate...clone pick
            pick_vals = {}
            if self.next_action == 'renumerate':
                new_pick = pick.copy() 
                note = _('%s\nPick renumerated from %s. %s') % (pick.note or '', pick.name, self.reason or '')
                new_pick.write({'note': note, 'origin': pick.name})
                new_picks.append(new_pick.id)
                pick_vals['renum_pick_id'] = new_pick.id

            # Cancelamos el picking actual y sus lineas
            moves_to_cancel = [m for m in pick.move_lines]
            pick_vals['state'] = 'cancel'
            pick.write(pick_vals)
            a = [move.write({'state': 'cancel'}) for move in moves_to_cancel]
        
        form = self.env.ref('stock.view_picking_form')
        
        if new_picks:
            if len(new_picks) == 1:
                return {
                    'res_model': 'stock.picking',
                    'type': 'ir.actions.act_window',
                    'views': [(form.id, 'form')],
                    'view_id': form.id,
                    'res_id': new_picks[0],
                }
            else:
                tree = self.env.ref('stock.action_picking_tree')
                return {
                    'res_model': 'stock.picking',
                    'type': 'ir.actions.act_window',
                    'views': [(tree.id, 'tree'), (form.id, 'form')],
                    'view_id': False,
                    'view_type': 'form',
                    'view_mode': 'tree,form',
                    'domain': [('id', 'in', new_picks)],
                }
