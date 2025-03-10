import logging
import os
import shutil

from odoo import tools

_logger = logging.getLogger(__name__)


def clean_pysfipws_cache(cr):
    FILESTORE_PATH = tools.config.filestore(cr.dbname)
    cache = os.path.join(FILESTORE_PATH, "cache")
    try:
        shutil.rmtree(cache)
    except OSError as e:
        _logger.info("Error: %s - %s." % (e.filename, e.strerror))
    return True


def migrate(cr, version):
    _logger.info("""Deleting pyafipws cache...""")
    clean_pysfipws_cache(cr)
    return True
