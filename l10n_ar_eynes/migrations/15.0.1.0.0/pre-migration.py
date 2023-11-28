import logging

import psycopg2

_logger = logging.getLogger(__name__)


def fix_wsfe_view(cr):
    try:
        cr.execute(
            """
            DELETE FROM ir_ui_view
            WHERE arch_db ilike '%homologation%'
                and model = 'wsfe.config'
            """
        )
    except psycopg2.ProgrammingError:
        cr.rollback()
    return True


def copy_wsfe_request_detail_to_ws_request_detail(cr):
    try:
        cr.execute(
            """
            CREATE TABLE ws_request_detail
                AS TABLE wsfe_request_detail;

            CREATE TABLE ws_request
                AS TABLE wsfe_request;

            CREATE UNIQUE INDEX ws_request_pkey
                ON public.ws_request USING btree (id);

            ALTER TABLE ws_request
                DROP COLUMN errors,
                DROP COLUMN name,
                DROP COLUMN result,
                DROP COLUMN reprocess;

            ALTER TABLE ws_request_detail
                ADD COLUMN pos_ar VARCHAR,
                ADD COLUMN voucher_type VARCHAR;

            UPDATE ws_request_detail
            SET
                pos_ar = ws_request.pos_ar,
                voucher_type = ws_request.voucher_type
            FROM ws_request
            WHERE ws_request.id = ws_request_detail.request_id;

            ALTER TABLE ws_request
            DROP COLUMN pos_ar,
            DROP COLUMN voucher_type;

            ALTER TABLE ws_request_detail
            RENAME name TO invoice_id;

            ALTER TABLE ws_request_detail
            RENAME cae_duedate TO cae_due_date;
            """
        )
    except psycopg2.ProgrammingError:
        cr.rollback()
    return True


def rename_wsfe_optionals(cr):
    try:
        cr.execute(
            """
            ALTER TABLE wsfe_optionals
            RENAME TO ws_optionals;
            ALTER TABLE wsfe_optionals_id_seq
            RENAME TO ws_optionals_id_seq;
            """
        )
    except psycopg2.ProgrammingError:
        cr.rollback()
    return True


def rename_wsfe_request_seq(cr):
    try:
        cr.execute(
            """
            ALTER TABLE wsfe_request_detail_id_seq
            RENAME TO ws_request_detail_id_seq;
            ALTER TABLE wsfe_request_id_seq
            RENAME TO ws_request_id_seq;
            """
        )
    except psycopg2.ProgrammingError:
        cr.rollback()
    return True


def delete_wsfex_request_detail_model(cr):
    try:
        cr.execute(
            """
            DELETE FROM ir_model_fields_selection
            WHERE field_id in (
                SELECT id FROM ir_model_fields
                WHERE model = 'wsfex.request.detail'
            );
            DELETE FROM ir_model_fields
            WHERE model = 'wsfex.request.detail';
            DELETE FROM ir_model_constraint
            WHERE model = (
                SELECT id FROM ir_model
                WHERE model = 'wsfex.request.detail'
            );
            DELETE FROM ir_model_relation
            WHERE model = (
                SELECT id FROM ir_model
                WHERE model = 'wsfex.request.detail'
            );
            DELETE FROM ir_model
            WHERE model = 'wsfex.request.detail';
            """
        )
    except psycopg2.ProgrammingError:
        cr.rollback()
    return True


def delete_wsfe_request_model(cr):
    try:
        cr.execute(
            """
            DELETE FROM ir_model_fields_selection
            WHERE field_id in (
                SELECT id FROM ir_model_fields
                WHERE model = 'wsfe.request'
            );
            DELETE FROM ir_model_fields
            WHERE model = 'wsfe.request';
            DELETE FROM ir_model_constraint
            WHERE model = (
                SELECT id FROM ir_model
                WHERE model = 'wsfe.request.detail'
            );
            DELETE FROM ir_model_relation
            WHERE model = (
                SELECT id FROM ir_model
                WHERE model = 'wsfe.request'
            );
            DELETE FROM ir_model
            WHERE model = 'wsfe.request';
            """
        )
    except psycopg2.ProgrammingError:
        cr.rollback()
    return True


def delete_wsfe_request_detail_model(cr):
    try:
        cr.execute(
            """
            DELETE FROM ir_model_fields_selection
            WHERE field_id in (
                SELECT id FROM ir_model_fields
                WHERE model = 'wsfe.request.detail'
            );
            DELETE FROM ir_model_fields
            WHERE model = 'wsfe.request.detail';
            DELETE FROM ir_model_constraint
            WHERE model = (
                SELECT id FROM ir_model
                WHERE model = 'wsfe.request.detail'
            );
            DELETE FROM ir_model_relation
            WHERE model = (
                SELECT id FROM ir_model
                WHERE model = 'wsfe.request.detail'
            );
            DELETE FROM ir_model
            WHERE model = 'wsfe.request.detail';
            """
        )
    except psycopg2.ProgrammingError:
        cr.rollback()
    return True


def migrate(cr, version):
    _logger.info("""Fixing WSFE view...""")
    fix_wsfe_view(cr)
    _logger.info("""Copying WSFE models to WS...""")
    copy_wsfe_request_detail_to_ws_request_detail(cr)
    _logger.info("""Rename WS models from WSFE and WSFEX...""")
    rename_wsfe_optionals(cr)
    rename_wsfe_request_seq(cr)
    _logger.info("""Deleting WSFE models...""")
    delete_wsfex_request_detail_model(cr)
    delete_wsfe_request_model(cr)
    delete_wsfe_request_detail_model(cr)
    return True
