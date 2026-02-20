from odoo import models, fields, _
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
import base64
from PyPDF2 import PdfReader, PdfWriter
from odoo.exceptions import UserError


class PrintCheckWizard(models.TransientModel):
    _name = 'print.check.wizard'
    _description = 'Print Check Wizard'

    checkbook_id = fields.Many2one(
        'account.payment.method.line',
        string='Checkbook',
        domain=[('code', '=', 'checks')],
    )
    check_template_id = fields.Many2one(
        'sign.oca.template', string='Check Template'
    )
    check_ids = fields.Many2many(
        'account.check',
        string='Checks to Print',
        domain="[('checkbook_id', '=', checkbook_id),('receiving_partner_id','!=', False),('check_printed','=',False)]",
    )  # [('checkbook_id', '=', checkbook_id)]

    def _mapping_checks_value(self, group):
        """
        Mapear campos del template con account.check
        """
        months = {
            1: 'Enero',
            2: 'Febrero',
            3: 'Marzo',
            4: 'Abril',
            5: 'Mayo',
            6: 'Junio',
            7: 'Julio',
            8: 'Agosto',
            9: 'Septiembre',
            10: 'Octubre',
            11: 'Noviembre',
            12: 'Diciembre',
        }
        currency = self.env.company.currency_id
        mapping = {
            'monto': group[0].amount if group[0].amount > 0 else "",
            'monto_escrito': currency.amount_to_text(group[0].amount)
            .replace("Peso", "")
            .strip()
            if group[0].amount > 0
            else "",
            'mes': months.get(group[0].payment_date.month, 'Mes Desconocido')
            or "",
            'año': str(group[0].payment_date.year) or "",
            'dia': str(group[0].payment_date.day) or "",
            'receptor': group[0].receiving_partner_id.name
            if group[0].receiving_partner_id
            else '',
            'monto2': group[1].amount
            if len(group) > 1 and group[1].amount > 0
            else "",
            'monto_escrito2': currency.amount_to_text(group[1].amount)
            .replace("Peso", "")
            .strip()
            if len(group) > 1 and group[1].amount > 0
            else "",
            'mes2': months.get(group[1].payment_date.month, 'Mes Desconocido')
            if len(group) > 1
            else "",
            'año2': str(group[1].payment_date.year) if len(group) > 1 else "",
            'dia2': str(group[1].payment_date.day) if len(group) > 1 else "",
            'receptor2': group[1].receiving_partner_id.name
            if len(group) > 1 and group[1].receiving_partner_id
            else '',
            'monto3': group[2].amount
            if len(group) > 2 and group[2].amount > 0
            else "",
            'monto_escrito3': currency.amount_to_text(group[2].amount)
            .replace("Peso", "")
            .strip()
            if len(group) > 2 and group[2].amount > 0
            else "",
            'mes3': months.get(group[2].payment_date.month, 'Mes Desconocido')
            if len(group) > 2
            else "",
            'año3': str(group[2].payment_date.year) if len(group) > 2 else "",
            'dia3': str(group[2].payment_date.day) if len(group) > 2 else "",
            'receptor3': group[2].receiving_partner_id.name
            if len(group) > 2 and group[2].receiving_partner_id
            else '',
            'monto4': group[3].amount
            if len(group) > 3 and group[3].amount > 0
            else "",
            'monto_escrito4': currency.amount_to_text(group[3].amount)
            .replace("Peso", "")
            .strip()
            if len(group) > 3 and group[3].amount > 0
            else "",
            'mes4': months.get(group[3].payment_date.month, 'Mes Desconocido')
            if len(group) > 3
            else "",
            'año4': str(group[3].payment_date.year) if len(group) > 3 else "",
            'dia4': str(group[3].payment_date.day) if len(group) > 3 else "",
            'receptor4': group[3].receiving_partner_id.name
            if len(group) > 3 and group[3].receiving_partner_id
            else '',
        }

        return mapping

    def _render_check_pdf(self, template, group):
        PAGE_WIDTH, PAGE_HEIGHT = A4

        # 1. PDF base
        base_pdf = PdfReader(BytesIO(base64.b64decode(template.data)))

        writer = PdfWriter()

        for page_index, base_page in enumerate(base_pdf.pages):
            buffer = BytesIO()
            c = canvas.Canvas(buffer, pagesize=A4)

            # 2. Campos del template para esta página
            items = template.item_ids.filtered(
                lambda i: i.page == page_index + 1
            )
            mapping = self._mapping_checks_value(group)
            for item in items:
                # 3. Obtener valor desde account.check
                value = mapping.get(item.field_id.name)
                if not value:
                    continue

                # 4. Conversión porcentaje → puntos
                PAGE_WIDTH * item.width / 100
                h = PAGE_HEIGHT * item.height / 100
                y = PAGE_HEIGHT - (PAGE_HEIGHT * item.position_y / 100) - h
                x = PAGE_WIDTH * item.position_x / 100

                # 5. Dibujar texto
                if item.field_id.name in [
                    'monto_escrito',
                    'monto_escrito2',
                    'monto_escrito3',
                    'monto_escrito4',
                ]:
                    c.setFont("Helvetica-Bold", 8)
                elif item.field_id.name in [
                    'monto',
                    'monto2',
                    'monto3',
                    'monto4',
                ]:
                    c.setFont("Helvetica-Bold", 14)
                else:
                    c.setFont("Helvetica", 10)

                # Texto centrado verticalmente
                c.drawString(x, y + h / 2, str(value))
            c.showPage()
            c.save()
            buffer.seek(0)

            overlay_pdf = PdfReader(buffer)
            base_page.merge_page(overlay_pdf.pages[0])
            writer.add_page(base_page)

        output = BytesIO()
        writer.write(output)
        output.seek(0)

        return base64.b64encode(output.read())

    def print_check(self):
        self.ensure_one()

        if not self.check_template_id:
            raise UserError(_("Debe seleccionar un template"))

        attachments = []
        grouped_in_4 = [
            self.check_ids[i : i + 4] for i in range(0, len(self.check_ids), 4)
        ]
        for group in grouped_in_4:
            pdf = self._render_check_pdf(self.check_template_id, group)

            attachment = self.env['ir.attachment'].create(
                {
                    'name': f'Cheque_{group[0].number}-{group[-1].number}.pdf',
                    'type': 'binary',
                    'datas': pdf,
                    'mimetype': 'application/pdf',
                }
            )

            attachments.append(attachment.id)
        for check in self.check_ids:
            check.write({'check_printed': True})
        # necesito poder juntar los pdfs generados en uno solo para descargarlo,
        # por ahora me descarga uno por cada 4 cheques
        # necesito que me descargue el pdf generado en lugar de mostrarme los adjuntos
        if len(attachments) == 1:
            return {
                'type': 'ir.actions.act_url',
                'url': f'/web/content/{attachments[0]}/{self.check_ids[0].number}?download=true',
                'target': 'self',
            }
        # juntar los pdfs en un solo pdf
        writer = PdfWriter()
        for attachment_id in attachments:
            attachment = self.env['ir.attachment'].browse(attachment_id)
            pdf_data = base64.b64decode(attachment.datas)
            reader = PdfReader(BytesIO(pdf_data))
            for page in reader.pages:
                writer.add_page(page)

        output = BytesIO()
        writer.write(output)
        output.seek(0)

        attachment = self.env['ir.attachment'].create(
            {
                'name': 'Cheques.pdf',
                'type': 'binary',
                'datas': base64.b64encode(output.read()),
                'mimetype': 'application/pdf',
            }
        )

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}/datas?download=true',
            'target': 'self',
        }
