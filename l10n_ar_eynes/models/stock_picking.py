##############################################################################
#
#   Copyright (c) 2022-2023 Eynes SRL  (Eynes - Ingenieria del software)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
#
##############################################################################

import codecs
import datetime
import logging
import os
import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..lib import cot

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _get_declared_value(self):
        Currency = self.env["res.currency"]

        sale_order = self.sale_id
        qty = 0
        aux = 0

        if self.pick_type == "outgoing":
            for move in self.move_lines:
                aux = move.product_qty * move.sale_line_id.price_unit

            qty += aux
            if qty != 0:
                if self.company_id.currency_id.id != sale_order.currency_id.id:
                    from_currency = sale_order.currency_id
                    to_currency = self.company_id.currency_id
                    qty = Currency._compute(
                        from_currency, to_currency, qty, round=False
                    )
        else:
            for move in self.move_lines:
                aux = move.product_qty * move.price_unit
                qty += aux
        return qty

    def button_validate(self):
        self.write({"declared_value": self._get_declared_value()})
        return super(StockPicking, self).button_validate()

    def is_refund(self):
        usage_origin = self.location_id.usage
        usage_dest = self.location_dest_id.usage

        if usage_origin == "internal" and usage_dest != "internal":
            return False
        elif usage_origin != "internal" and usage_dest == "internal":
            return True
        else:
            return False

    def get_cuit(self, company):
        if company:
            if not company.vat:
                raise ValidationError(
                    _("COT Error" "\n- %s's NIF code is null") % (company.name),
                )
        else:
            if not self.partner_id:
                raise ValidationError(_("COT Error\n- No partner found"))
            elif not self.carrier_id:
                raise ValidationError(_("COT Error\n- No carrier found"))

        cuit = re.search(r"\d{11}", str(company.vat))
        if cuit:
            return cuit.group(0)
        else:
            raise ValidationError(
                _("COT Error\n- %s's NIF is invalid") % (company.name)
            )

    def get_sequence(self):
        try:
            prefix, sufix = self.name.split("-")

            sequence = re.search(
                r"(\d{5})-(\d{8})", "%05d-%08d" % (int(prefix), int(sufix))
            )

            if sequence:
                return "091" + sequence.group(1) + sequence.group(2)
        except BaseException:
            raise ValidationError from None(
                _("COT Error\n- Invalid sequence: %s") % (self.name)
            )

    def is_valid_date(self, date):
        date_transport = date
        today = datetime.date.today()
        max_date = today + datetime.timedelta(days=30)

        if date_transport >= today and date_transport <= max_date:
            return date_transport
        else:
            return False

    def cot_remit(self):
        vals = self.get_remit_vals()
        return (
            "02|"
            + vals['date']
            + "|"
            + vals['unique_code']
            + "|"
            + vals['date_transport']
            + "|"
            + vals['time_transport']
            + "|"
            + vals['subject']
            + "|"
            + str(vals['is_final_consumer'])
            + "| | |"
            + vals['partner_cuit']
            + "|"
            + vals['partner_reason_social']
            + "|"
            + vals['dest_tenedor']
            + "|"
            + vals['partner_street']
            + "|"
            + vals['partner_number']
            + "|"
            + vals['partner_comple']
            + "|"
            + vals['partner_floor']
            + "|"
            + vals['partner_departament']
            + "| |"
            + vals['partner_zip']
            + "|"
            + vals['partner_city']
            + "|"
            + vals['partner_cod_state']
            + "| |"
            + vals['origin']
            + "|"
            + vals['company_cuit']
            + "|"
            + vals['company_reason_social']
            + "|"
            + str(vals['tenedor'])
            + "|"
            + vals['company_street']
            + "|"
            + vals['company_number']
            + "|"
            + vals['company_comple']
            + "|"
            + vals['company_floor']
            + "|"
            + vals['company_departament']
            + "| |"
            + vals['company_zip']
            + "|"
            + vals['company_city']
            + "|"
            + vals['company_cod_state']
            + "|"
            + vals['carrier_cuit']
            + "|"
            + vals['type_path']
            + "| | | |"
            + vals['license_plate']
            + "|"
            + vals['trailer_license_plate']
            + "|"
            + str(vals['refund'])
            + "|"
            + str(vals['import_value'])
            + "\n"
        )

    def get_remit_vals(self):
        """returns a dictionary with the values that will ve use to generate
        the COT remit
        """
        vals = {}
        vals.update(self._get_partner_vals())
        vals.update(self._get_company_vals())

        if not self.declared_value:
            dec_value = self._get_declared_value()
            self.write({"declared_value": dec_value})
            import_value = str(int(dec_value * 100))
        else:
            import_value = str(int(self.declared_value * 100))

        if self.cot_date_transfer:
            date_t = self.is_valid_date(self.cot_date_transfer)

            if date_t:
                date_transport = date_t.strftime("%Y%m%d")
                time_transport = date_t.strftime("0000")
            else:
                raise ValidationError(_("COT Error\n- Invalid emission date"))
        else:
            raise ValidationError(
                _("COT Error\n- Transport departure date is null")
            )

        if self.truck_license_plate:
            license_plate = self.truck_license_plate.upper()
            trailer_license_plate = self.trailer_license_plate
            if trailer_license_plate:
                trailer_license_plate = trailer_license_plate.upper()
            else:
                trailer_license_plate = ""
        else:
            raise ValidationError(_("COT Error\n- License plate is null"))

        if self.is_origin:
            origin = "SI"
        else:
            origin = "NO"

        subject = "E"

        if self.partner_id.express_id:
            dest_tenedor = "1"
        else:
            dest_tenedor = "0"

        tenedor = 0

        vals.update(
            {
                'import_value': import_value,
                'date_transport': date_transport,
                'time_transport': time_transport,
                'license_plate': license_plate,
                'origin': origin,
                'subject': subject,
                'dest_tenedor': dest_tenedor,
                'tenedor': tenedor,
            }
        )

    def _get_partner_vals(self):
        """Get partner values for the remit and perform values validations"""
        date = datetime.datetime.now().strftime("%Y%m%d")
        express_id = self.partner_id.express_id

        if not express_id:
            is_final_consumer = int(
                self.partner_id.property_account_position_id.is_final_consumer
            )
        else:
            is_final_consumer = int(
                express_id.property_account_position_id.is_final_consumer
            )

        carrier_cuit = self.get_cuit(self.carrier_id)

        type_path = "U"
        refund = int(self.is_refund())
        if not express_id:
            partner_cuit = self.get_cuit(self.partner_id)
            partner_cod_state = self.partner_id.state_id.cot_code
            partner_zip = self.partner_id.zip
            partner_city = self.partner_id.city
            partner_street = self.partner_id.street
            partner_reason_social = (
                self.partner_id.name + " " + (self.partner_id.title.name or "")
            )
            partner_floor = self.partner_id.floor or ""
            partner_departament = self.partner_id.apartment or ""
            partner_number = self.partner_id.num or ""
        else:
            partner_cuit = self.get_cuit(express_id)
            partner_cod_state = express_id.state_id.cot_code
            partner_zip = express_id.zip
            partner_city = express_id.city
            partner_street = express_id.street
            partner_reason_social = (
                express_id.name + " " + (express_id.title.name or "")
            )
            partner_floor = express_id.floor or ""
            partner_departament = express_id.apartment or ""
            partner_number = express_id.num or ""
        if partner_number:
            partner_comple = ""
        else:
            partner_comple = "S/N"

        if not partner_city:
            if not express_id:
                raise ValidationError(
                    _("COT Error\n- %s does not have a city name")
                    % (self.partner_id.name),
                )
            else:
                raise ValidationError(
                    _("COT Error\n- Express %s does not have a city name")
                    % (express_id.name),
                )
        if not partner_zip:
            if not express_id:
                raise ValidationError(
                    _("COT Error\n- %s does not have a postal code")
                    % (self.partner_id.name),
                )
            else:
                raise ValidationError(
                    _("COT Error\n- Express %s does not have a postal code")
                    % (express_id.name),
                )
        if not partner_street:
            if not express_id:
                raise ValidationError(
                    _("COT Error\n- %s does not have a street name")
                    % (self.partner_id.name),
                )
            else:
                raise ValidationError(
                    _("COT Error\n- Express %s does not have a street name")
                    % (express_id.name),
                )
        if not partner_cod_state:
            if not express_id:
                raise ValidationError(
                    _("COT Error\n- %s does not have a state code")
                    % (self.partner_id.name),
                )
            else:
                raise ValidationError(
                    _("COT Error\n- Express %s does not have a state code")
                    % (express_id.name),
                )

        return {
            'date': date,
            'express_id': express_id,
            'is_final_consumer': is_final_consumer,
            'carrier_cuit': carrier_cuit,
            'type_path': type_path,
            'refund': refund,
            'partner_cuit': partner_cuit,
            'partner_cod_state': partner_cod_state,
            'partner_zip': partner_zip,
            'partner_city': partner_city,
            'partner_street': partner_street,
            'partner_reason_social': partner_reason_social,
            'partner_floor': partner_floor,
            'partner_departament': partner_departament,
            'partner_number': partner_number,
            'partner_comple': partner_comple,
        }

    def _get_company_vals(self):
        """Get company values for the remit and perform values validations"""
        company_cuit = self.get_cuit(self.company_id)
        company_cod_state = self.company_id.state_id.cot_code
        company_zip = self.company_id.zip
        company_city = self.company_id.city
        company_street = self.company_id.street
        company_reason_social = self.company_id.name
        company_floor = self.company_id.floor or ""
        company_departament = self.company_id.apartment or ""
        company_number = self.company_id.num or ""
        unique_code = self.get_sequence()
        if company_number:
            company_comple = ""
        else:
            company_comple = "S/N"
        if not company_city:
            raise ValidationError(
                _("COT Error\n- Your company does not have a city name")
            )

        if not company_zip:
            raise ValidationError(
                _("COT Error\n- Your company does not have a postal code"),
            )

        if not company_street:
            raise ValidationError(
                _("COT Error\n- Your company does not have a street name"),
            )

        if not company_cod_state:
            raise ValidationError(
                _("COT Error\n- Your company does not have a state code")
            )
        return {
            'company_cuit': company_cuit,
            'company_cod_state': company_cod_state,
            'company_zip': company_zip,
            'company_city': company_city,
            'company_street': company_street,
            'company_reason_social': company_reason_social,
            'company_floor': company_floor,
            'company_departament': company_departament,
            'company_number': company_number,
            'unique_code': unique_code,
            'company_comple': company_comple,
        }

    def cot_product(self):
        ls_product = []
        for line in self.move_lines:
            product_qty = str(int(line.product_qty * 100))
            product_code = str(line.product_id.default_code)[:25]
            product_desc = line.name
            product_uom_categ = str(line.product_uom.category_id.name)[:20]
            product_uom_code = line.product_uom.cot_code
            product_nomenclature = line.product_id.cot_nomenclature_id.code

            if product_desc:
                product_desc = line.name.replace("\n", "")[:40]
            else:
                raise ValidationError(
                    _("COT Error\n- %s, product description is null")
                    % (product_desc),
                )

            if len(product_qty) > 15:
                raise ValidationError(
                    _("COT Error\n- %s, The quantity is out of range")
                    % (product_desc),
                )

            if not product_nomenclature:
                raise ValidationError(
                    _("COT Error\n- %s: COT nomenclature is null")
                    % (product_desc),
                )

            if not product_uom_code:
                raise ValidationError(
                    _("COT Error\n- %s: UOM's COT code is null")
                    % (product_desc),
                )

            ls_product.append(
                "03|"
                + product_nomenclature
                + "|"
                + product_uom_code
                + "|"
                + product_qty
                + "|"
                + product_code
                + "|"
                + product_desc
                + "|"
                + product_uom_categ
                + "|"
                + product_qty
                + "\n"
            )
        return ls_product

    def do_cot_file(self):
        cuit = self.get_cuit(self.company_id)
        floor = self.company_id.floor or "000"
        door = self.company_id.door or "000"
        date = datetime.date.today().strftime("%Y%m%d")
        sequence = self.get_sequence()[-6:]
        express_id = self.partner_id.express_id
        URL = self._get_cot_url()

        # file name
        fileName = (
            "/tmp/"
            + "TB_"
            + cuit
            + "_"
            + floor.zfill(3)
            + door.zfill(3)
            + "_"
            + date
            + "_"
            + sequence
            + ".txt"
        )

        cot_header = "01|" + cuit + "\n"
        cot_remit = self.cot_remit()
        cot_product = self.cot_product()
        cot_footer = "04|1"
        cot_error = ""

        file = codecs.open(fileName, "w", "utf-8")
        file.write(cot_header)
        file.write(cot_remit)
        file.writelines(cot_product)
        file.write(cot_footer)
        file.close()

        cot_obj = cot.COT()
        cot_obj.Password = self._get_cot_pass()
        cot_obj.Usuario = self._get_cot_user()

        # cot_obj.Usuario = cuit
        # TODO: Hacer la verificación del SSL
        cot_obj.Conectar(URL, trace=False, cacert=None)

        cot_obj.PresentarRemito(fileName, testing="")

        os.remove(fileName)

        if cot_obj.Excepcion:
            raise ValidationError(
                _(
                    "COT Errorn- Exception: %(exception)s\nTraceback: %(traceback)s",
                    exception=cot_obj.Excepcion,
                    traceback=cot_obj.Traceback,
                ),
            )

        if cot_obj.CodigoError == "":
            # Compruebo que el remito este correcto
            cot_obj.LeerValidacionRemito()

            # Hay varios errores? Solo el ultimo error es el importante
            while cot_obj.LeerErrorValidacion():
                cot_error = ("Error %s \n %s") % (
                    cot_obj.CodigoError,
                    cot_obj.MensajeError,
                )

            if cot_error != "":
                raise ValidationError(_("COT Error\n- %s") % (cot_error))

            # Agarro el numero de remito y su comprobante.
            cot_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cot_code = self.get_sequence()
            voucher = cot_obj.NumeroComprobante
            self.write(
                {
                    "cot_date": cot_date,
                    "cot": cot_code,
                    "voucher": voucher,
                    "express_id": express_id.id,
                }
            )
        else:
            raise ValidationError(
                _(
                    "COT Error\nError %(err_code)s  Type: %(err_type)s \n %(err_msg)s",
                    err_code=cot_obj.CodigoError,
                    err_type=cot_obj.TipoError,
                    err_msg=cot_obj.MensajeError,
                )
            )
        return True

    def _get_cot_user(self):
        # Obtenemos el user (CUIT) del COT
        config_obj = self.env["ir.config_parameter"].sudo()
        cot_user = config_obj.get_param("cot_user", default="CUIT")
        return cot_user

    def _get_cot_pass(self):
        # Obtenemos la password del cot
        config_obj = self.env["ir.config_parameter"].sudo()
        cot_pass = config_obj.get_param("cot_pass", default="Password")
        return cot_pass

    def _get_cot_url(self):
        # Obtenemos la url para enviar el remito
        config_obj = self.env["ir.config_parameter"].sudo()
        cot_url = config_obj.get_param("cot_url", default="http://arba.gov.ar/")
        return cot_url

    @api.onchange("carrier_id")
    def onchange_carrier(self):
        if self.carrier_id:
            self.dom_partner_id = self.carrier_id.id

    # route_id = fields.Many2one("delivery.route")
    # route_state = fields.Selection(related="route_id.state")
    declared_value = fields.Float(
        "Declared Value",
        readonly=True,
        help="Declared Value",
    )
    cot = fields.Char("COT", readonly=True, copy=False, help="COT Code")
    picking_supplier = fields.Char("Picking Supplier", size=100)
    voucher = fields.Char("Voucher", readonly=True, copy=False)
    cot_date = fields.Datetime("Cot Date", readonly=True, copy=False)
    is_origin = fields.Boolean("Delivey an origin", help="Delivery Origin")
    # cot_date_transfer = fields.Date(
    #     related="route_id.date",
    #     string="Date of Transfer",
    #     help="Date of Transport Depature",
    # )
    express_id = fields.Many2one("res.partner", "Express", readonly=True)
    # truck_license_plate = fields.Char(
    #     related="route_id.scale_entry_id.truck_id.name",
    #     string="Truck License Plate",
    # )
    # trailer_license_plate = fields.Char(
    #     related="route_id.scale_entry_id.trailer_id.name",
    #     string="Trailer License Plate",
    # )
    dimension = fields.Float("Dimension")
    pick_type = fields.Selection(
        string="Type",
        related="picking_type_id.code",
        store=True,
        readonly=True,
    )
    dom_partner_id = fields.Many2one("res.partner", string="Carrier Partner")
