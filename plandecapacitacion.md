# Plan de capacitación (5 días, 2h/día)

## Lunes — Facturación local y base fiscal
### Qué se hace
- Mapa del módulo y dependencias: `l10n_ar_eynes/__manifest__.py`, `readme.md`
- Documentos y vouchers: `l10n_ar_eynes/models/res_document_type.py`, `l10n_ar_eynes/models/res_voucher_type.py`
- Factura local y diarios: `l10n_ar_eynes/models/account_move.py`, `l10n_ar_eynes/models/account_journal.py`
- UI de facturas: `l10n_ar_eynes/views/account_move_views.xml`, `l10n_ar_eynes/views/account_journal_views.xml`

### Checklist
- [ ] Revisado `l10n_ar_eynes/__manifest__.py` y explicado alcance + dependencias.
- [ ] Identificados campos AFIP en `l10n_ar_eynes/models/res_document_type.py`.
- [ ] Identificados campos AFIP en `l10n_ar_eynes/models/res_voucher_type.py`.
- [ ] Explicado cómo se valida documento/VAT del partner.
- [ ] Localizados campos fiscales en `l10n_ar_eynes/models/account_move.py`.
- [ ] Explicada selección de `voucher_type_id` y `fiscal_type`.
- [ ] Revisadas vistas `l10n_ar_eynes/views/account_move_views.xml`.
- [ ] Revisadas vistas `l10n_ar_eynes/views/account_journal_views.xml`.

---

## Martes — Percepciones y Retenciones
### Qué se hace
- Percepciones: `l10n_ar_eynes/models/perception.py`, `l10n_ar_eynes/views/perception_view.xml`
- Retenciones: `l10n_ar_eynes/models/retention.py`, `l10n_ar_eynes/views/retention_views.xml`
- Relación con impuestos: `l10n_ar_eynes/models/account_tax.py`, `l10n_ar_eynes/models/account_tax_group.py`

### Checklist
- [ ] Identificado cuándo se crea `perception.tax.line`.
- [ ] Explicada lógica de base y monto en percepciones.
- [ ] Revisadas validaciones de base/importe en percepciones.
- [ ] Explicado cálculo en moneda secundaria en percepciones.
- [ ] Identificados conceptos y actividades en retenciones.
- [ ] Explicada lógica de `retention.tax.application`.
- [ ] Explicada diferencia `aliq_type=percent` vs `aliq_type=scale`.
- [ ] Confirmada relación con impuestos en `account_tax.py`.

---

## Miércoles — AFIP WSAA / WSFE
### Qué se hace
- WSAA (auth y tokens): `l10n_ar_eynes/models/wsaa.py`
- WSFE config y tablas: `l10n_ar_eynes/models/wsfe.py`, `l10n_ar_eynes/models/ws.py`
- Parsing y validación: `l10n_ar_eynes/wsfetools/wsfe_helper.py`, `l10n_ar_eynes/wsfetools/ws_afip.py`
- WS Padron (visión breve): `l10n_ar_eynes/models/ws_padron.py`

### Checklist
- [ ] Explicado flujo WSAA en `wsaa.py`.
- [ ] Ubicado dónde se guardan certificados y keys.
- [ ] Explicado `get_token_sign` y expiración de token.
- [ ] Revisadas tablas AFIP en `wsfe.py`.
- [ ] Explicada relación POS AFIP ↔ journal (`ws.pos.line`).
- [ ] Revisado `parse_invoice` en `wsfe_helper.py`.
- [ ] Revisado `parse_vat_lines` y validación de impuestos.
- [ ] Identificado manejo de errores en `ws_afip.py`.

---

## Jueves — Exportadores regulatorios
### Qué se hace
- SICORE/SIFERE: `l10n_ar_eynes/models/sicore.py`, `l10n_ar_eynes/models/sifere.py`
- ARBA/ARCIBA + formatos: `l10n_ar_eynes/models/*exporter*.py`, `l10n_ar_eynes/utils/*_fixed_width_dicts.py`
- Wizards de exportación: `l10n_ar_eynes/wizard/create_*_file.py`
- Reportes fiscales: `l10n_ar_eynes/report/*`

### Checklist
- [ ] Revisado modelo de SICORE.
- [ ] Revisado modelo de SIFERE.
- [ ] Identificados diccionarios de formatos fixed-width.
- [ ] Explicado mapeo ARBA/ARCIBA desde partner y factura.
- [ ] Revisados wizards `create_*_file.py`.
- [ ] Confirmadas validaciones previas a generar archivos.
- [ ] Revisados reportes fiscales clave.

---

## Viernes — Cobros, cheques, POS y Padron WS
### Qué se hace
- Órdenes de pago/recibo: `l10n_ar_eynes/models/account_payment_order.py`
- Cheques y estados: `l10n_ar_eynes/models/account_check.py`, `l10n_ar_eynes/wizard/*check*`
- POS + WSFE: `l10n_ar_pos_wsfe/models/pos_order.py`
- Padron WS Consumer: `l10n_ar_padron_ws_consumer/models/res_partner.py`, `l10n_ar_padron_ws_consumer/data/cron_data.xml`

### Checklist
- [ ] Explicado flujo de `account.payment.order` de draft a posted.
- [ ] Explicado cálculo de `writeoff_amount` y conciliación.
- [ ] Identificados asientos generados en pago/recibo.
- [ ] Explicados estados y movimientos en `account.check`.
- [ ] Diferenciado cheque `issued` vs `third_party`.
- [ ] Revisado `_generate_pos_order_invoice` en POS WSFE.
- [ ] Explicado disparo de WSFE desde POS.
- [ ] Explicado flujo de actualización Padron WS consumer.
- [ ] Confirmada lógica de selección de journal por provincia.