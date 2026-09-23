import json, os
from app.services.storage import get_staging_json, get_approved_json

k_id = '3dc6c820-59e1-4be6-8c9f-b5313cb91623'
staging_data = get_staging_json(k_id)
print('STAGING DATA FROM MINIO:', bool(staging_data))
if staging_data:
    summary = staging_data.get('summary', '')
    print('STAGING SUMMARY HAS EXFOLIATING SCRUB:', 'Exfoliating Cleansing Scrub' in summary)
    print('STAGING CHUNKS COUNT:', len(staging_data.get('chunks', [])))

approved_data = get_approved_json(k_id)
print('APPROVED DATA FROM MINIO:', bool(approved_data))
if approved_data:
    summary = approved_data.get('summary', '')
    print('APPROVED SUMMARY HAS EXFOLIATING SCRUB:', 'Exfoliating Cleansing Scrub' in summary)
    print('APPROVED CHUNKS COUNT:', len(approved_data.get('chunks', [])))
