# Migración de ir.model.data:
# l10n_ar_eynes.<name>  ->  account.<company_id>_<name>
#
# Modelos: account.journal, account.tax, account.tax.group

import logging

_logger = logging.getLogger(__name__)


def _log(msg, **kw):
    if kw:
        msg = msg + " | " + " ".join(f"{k}={v}" for k, v in kw.items())
    _logger.info(msg)


def migrate_account_journal(cr):
    model = "account.journal"
    table = "account_journal"
    _log("Procesando modelo", model=model, table=table)

    cr.execute(
        f"""
        SELECT
            imd.id       AS imd_id,
            imd.module   AS old_module,
            imd.name     AS old_name,
            imd.res_id   AS res_id,
            j.company_id AS company_id
        FROM ir_model_data imd
        JOIN {table} j ON j.id = imd.res_id
        WHERE imd.model  = %s
          AND imd.module = 'l10n_ar_eynes'
        ORDER BY imd.id
    """,
        (model,),
    )
    rows = cr.fetchall()

    total = len(rows)
    done, skipped, collisions = 0, 0, 0

    for (imd_id, old_module, old_name, res_id, company_id) in rows:
        old_xid = f"{old_module}.{old_name}"

        if not company_id:
            skipped += 1
            _log(
                "SKIP: journal sin company_id",
                imd_id=imd_id,
                res_id=res_id,
                old_xid=old_xid,
            )
            continue

        base = f"{company_id}_{old_name}"

        cr.execute(
            """
            SELECT id
              FROM ir_model_data
             WHERE module = 'account'
               AND name   = %s
               AND model  = %s
             LIMIT 1
        """,
            (base, model),
        )
        exists = cr.fetchone()

        if exists:
            final_name = f"{base}_{res_id}"
            collisions += 1
            collision = True
        else:
            final_name = base
            collision = False

        cr.execute(
            """
            UPDATE ir_model_data
               SET module = 'account',
                   name   = %s
             WHERE id = %s
        """,
            (final_name, imd_id),
        )

        done += 1
        _log(
            "UPDATE IMD (journal)",
            imd_id=imd_id,
            res_id=res_id,
            company_id=company_id,
            old_xid=old_xid,
            new_xid=f"account.{final_name}",
            collision=collision,
        )

    _log(
        "Resumen modelo",
        model=model,
        total=total,
        actualizados=done,
        saltados_sin_company=skipped,
        colisiones_resueltas=collisions,
    )


def migrate_account_tax(cr):
    model = "account.tax"
    table = "account_tax"
    _log("Procesando modelo", model=model, table=table)

    cr.execute(
        f"""
        SELECT
            imd.id       AS imd_id,
            imd.module   AS old_module,
            imd.name     AS old_name,
            imd.res_id   AS res_id,
            t.company_id AS company_id
        FROM ir_model_data imd
        JOIN {table} t ON t.id = imd.res_id
        WHERE imd.model  = %s
          AND imd.module = 'l10n_ar_eynes'
        ORDER BY imd.id
    """,
        (model,),
    )
    rows = cr.fetchall()

    total = len(rows)
    done, skipped, collisions = 0, 0, 0

    for (imd_id, old_module, old_name, res_id, company_id) in rows:
        old_xid = f"{old_module}.{old_name}"

        if not company_id:
            skipped += 1
            _log(
                "SKIP: tax sin company_id",
                imd_id=imd_id,
                res_id=res_id,
                old_xid=old_xid,
            )
            continue

        base = f"{company_id}_{old_name}"

        cr.execute(
            """
            SELECT id
              FROM ir_model_data
             WHERE module = 'account'
               AND name   = %s
               AND model  = %s
             LIMIT 1
        """,
            (base, model),
        )
        exists = cr.fetchone()

        if exists:
            final_name = f"{base}_{res_id}"
            collisions += 1
            collision = True
        else:
            final_name = base
            collision = False

        cr.execute(
            """
            UPDATE ir_model_data
               SET module = 'account',
                   name   = %s
             WHERE id = %s
        """,
            (final_name, imd_id),
        )

        done += 1
        _log(
            "UPDATE IMD (tax)",
            imd_id=imd_id,
            res_id=res_id,
            company_id=company_id,
            old_xid=old_xid,
            new_xid=f"account.{final_name}",
            collision=collision,
        )

    _log(
        "Resumen modelo",
        model=model,
        total=total,
        actualizados=done,
        saltados_sin_company=skipped,
        colisiones_resueltas=collisions,
    )


def migrate_account_tax_group(cr):
    model = "account.tax.group"
    table = "account_tax_group"
    _log("Procesando modelo", model=model, table=table)

    cr.execute(
        f"""
        SELECT
            imd.id       AS imd_id,
            imd.module   AS old_module,
            imd.name     AS old_name,
            imd.res_id   AS res_id,
            g.company_id AS company_id
        FROM ir_model_data imd
        JOIN {table} g ON g.id = imd.res_id
        WHERE imd.model  = %s
          AND imd.module = 'l10n_ar_eynes'
        ORDER BY imd.id
    """,
        (model,),
    )
    rows = cr.fetchall()

    total = len(rows)
    done, skipped, collisions = 0, 0, 0

    for (imd_id, old_module, old_name, res_id, company_id) in rows:
        old_xid = f"{old_module}.{old_name}"

        if not company_id:
            skipped += 1
            _log(
                "SKIP: tax_group sin company_id",
                imd_id=imd_id,
                res_id=res_id,
                old_xid=old_xid,
            )
            continue

        base = f"{company_id}_{old_name}"

        cr.execute(
            """
            SELECT id
              FROM ir_model_data
             WHERE module = 'account'
               AND name   = %s
               AND model  = %s
             LIMIT 1
        """,
            (base, model),
        )
        exists = cr.fetchone()

        if exists:
            final_name = f"{base}_{res_id}"
            collisions += 1
            collision = True
        else:
            final_name = base
            collision = False

        cr.execute(
            """
            UPDATE ir_model_data
               SET module = 'account',
                   name   = %s
             WHERE id = %s
        """,
            (final_name, imd_id),
        )

        done += 1
        _log(
            "UPDATE IMD (tax_group)",
            imd_id=imd_id,
            res_id=res_id,
            company_id=company_id,
            old_xid=old_xid,
            new_xid=f"account.{final_name}",
            collision=collision,
        )

    _log(
        "Resumen modelo",
        model=model,
        total=total,
        actualizados=done,
        saltados_sin_company=skipped,
        colisiones_resueltas=collisions,
    )


def migrate(cr, version):
    _log(
        "=== Inicio migración de ir.model.data → account.<company_id>_<name> ==="
    )
    migrate_account_journal(cr)
    migrate_account_tax(cr)
    migrate_account_tax_group(cr)
    _log("=== Fin migración de ir.model.data ===")
