import json, sys
from app.rag.services.general_knowledge_service import resolve_approved_file
from app.rag.services.vector_store import PGVectorAdapter

k_id = '3dc6c820-59e1-4be6-8c9f-b5313cb91623'
p = resolve_approved_file(k_id)
print('APPROVED FILE PATH:', p)
if p:
    with open(p, 'r', encoding='utf-8') as f:
        doc = json.load(f)
    print('DOC TITLE:', doc.get('title'))
    print('CHUNKS IN JSON FILE:', len(doc.get('chunks', [])))
    for i, c in enumerate(doc.get('chunks', [])):
        txt = (c.get('text') or '').replace('\n', ' ')
        print(f'JSON CHUNK {i}: {txt[:120]}')

vs = PGVectorAdapter()
pg_chunks = vs.search(k_id, top_k=10)
print('PGVECTOR CHUNKS FOUND:', len(pg_chunks))
for i, c in enumerate(pg_chunks):
    txt = (c.get('text') or '').replace('\n', ' ')
    print(f'PG CHUNK {i}: {txt[:120]}')
