# import logging
# import xml.etree.ElementTree as ET
# import os

# from itertools import chain
# logger = logging.getLogger(__name__)


# def pre_init_hook(cr):
#     base_dir = os.path.dirname(os.path.realpath(__file__))
#     perceptions_tree = ET.parse(base_dir + '/../l10n_ar_eynes/data/perceptions.xml')
#     retentions_tree = ET.parse(base_dir + './l10n_ar_eynes/data/retentions.xml')
#     logger.info("Check if already exists related ir_model_data related to account.journal data for Padron WS")
#     logger.info("Checking perceptions")
#     chained = chain(perceptions_tree.getroot().iter('record'), retentions_tree.getroot().iter('record'))
#     for record in chained:
#         name = record.attrib.get('id')
#         code = record.find(".//field[@name='code']").text
#         cr.execute("SELECT id from account_journal WHERE code = %s", (code,))
#         res_id = cr.fetchone()
#         if res_id:
#             cr.execute("""
#                 INSERT INTO ir_model_data (name, model, module, res_id, noupdate)
#                        SELECT %s, %s, %s, %s, %s
#                 WHERE NOT EXISTS (
#                     SELECT name FROM ir_model_data WHERE name = %s);
#                 """, (name, 'account.journal', 'l10n_ar_eynes', res_id[0], True, name)
#             )
