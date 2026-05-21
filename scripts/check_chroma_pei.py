#!/usr/bin/env python3
import os
from pathlib import Path
from dotenv import load_dotenv

# Load project .env
base = Path(__file__).resolve().parents[1]
env_path = base / '.env'
if env_path.exists():
    load_dotenv(env_path)

from vector_store import VectorStore

def main():
    doc_id = '9b28f436-39c5-42ae-8804-57883b7ebca5'
    vs = VectorStore()
    print('Collection count:', vs.count())
    doc = vs.get_document(doc_id)
    print('get_document result:')
    print(doc)

    print('\nTrying summarize_student_documents (if student_name known):')
    # no student name known here; show list_documents
    docs = vs.list_documents()
    print('list_documents count:', len(docs))
    for d in docs[:10]:
        print(d)

if __name__ == '__main__':
    main()
