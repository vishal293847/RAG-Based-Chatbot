from pymongo import MongoClient
from bson import ObjectId
from elasticsearch import Elasticsearch, helpers
import re
import os
from dotenv import load_dotenv

# -----------------------------
# CONFIG
# -----------------------------
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = "docs_backend"

ES_HOST = os.getenv("ES_HOST")
ES_USER = os.getenv("ES_USER")
ES_PASS = os.getenv("ES_PASS")

INDEX_NAME = "mxy-chatbot_v2"

# -----------------------------
# CONNECTIONS
# -----------------------------
mongo_client = MongoClient(MONGO_URI)
db = mongo_client[DB_NAME]

docs_col = db["docs"]
tags_col = db["tags"]
categories_col = db["categories"]

es = Elasticsearch(
    ES_HOST,
    basic_auth=(ES_USER, ES_PASS)
)

# -----------------------------
# HELPERS
# -----------------------------
def clean_text(text):
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def chunk_text(text, max_words=200):
    words = text.split()
    return [' '.join(words[i:i+max_words]) for i in range(0, len(words), max_words)]

# -----------------------------
# TAG MAP
# -----------------------------
def get_tag_map():
    tag_map = {}
    tags = tags_col.find({"isdelete": {"$ne": True}})
    for tag in tags:
        tag_map[str(tag["_id"])] = tag.get("name", "unknown")
    return tag_map

# -----------------------------
# MARKETXY TAG IDS
# -----------------------------
def get_marketxy_tag_ids():
    tags = tags_col.find({
        "name": {"$regex": "marketxy", "$options": "i"}
    })
    return [tag["_id"] for tag in tags]

# -----------------------------
# DOC FETCHING
# -----------------------------
def get_docs_by_tags(tag_ids):
    return list(docs_col.find({
        "tags": {"$in": tag_ids},
        "isdelete": {"$ne": True}
    }))

def get_related_categories(docs):
    doc_ids = [doc["_id"] for doc in docs]

    categories = categories_col.find({
        "docs": {"$in": doc_ids},
        "isdelete": {"$ne": True}
    })

    return list(categories)

def get_docs_from_categories(categories):
    all_doc_ids = set()

    for cat in categories:
        for doc_id in cat.get("docs", []):
            all_doc_ids.add(doc_id)

    return list(docs_col.find({
        "_id": {"$in": list(all_doc_ids)},
        "isdelete": {"$ne": True}
    }))

# -----------------------------
# BUILD CHUNKS
# -----------------------------
def build_chunks(doc, tag_map):
    text = clean_text(doc.get("content", ""))
    if not text:
        return []

    chunks = chunk_text(text)

    tag_names = [
        tag_map.get(str(t), "unknown")
        for t in doc.get("tags", [])
        if str(t) in tag_map
    ]

    results = []

    for i, chunk in enumerate(chunks):
        if not chunk or len(chunk.split()) < 20:
            continue

        results.append({
            "doc_id": str(doc["_id"]),
            "chunk_id": f"{doc['_id']}_{i}",
            "content": chunk,
            "tags": tag_names
        })

    return results

# -----------------------------
# STORE IN ELASTICSEARCH
# -----------------------------
def store_in_elasticsearch(all_chunks):
    actions = []

    for chunk in all_chunks:
        actions.append({
            "_index": INDEX_NAME,
            "_id": chunk["chunk_id"],  # unique id
            "_source": chunk
        })

        # Bulk insert every 500 docs
        if len(actions) >= 500:
            helpers.bulk(es, actions)
            actions = []

    # Final flush
    if actions:
        helpers.bulk(es, actions)

# -----------------------------
# MAIN PIPELINE
# -----------------------------
def run_pipeline():
    tag_map = get_tag_map()

    # Step 1
    tag_ids = get_marketxy_tag_ids()

    # Step 2
    tag_docs = get_docs_by_tags(tag_ids)

    # Step 3
    categories = get_related_categories(tag_docs)

    # Step 4
    category_docs = get_docs_from_categories(categories)

    # Combine (remove duplicates)
    all_docs_map = {str(doc["_id"]): doc for doc in tag_docs}
    for doc in category_docs:
        all_docs_map[str(doc["_id"])] = doc

    all_docs = list(all_docs_map.values())

    print(f"📄 Total docs: {len(all_docs)}")

    # Chunking
    all_chunks = []
    for doc in all_docs:
        chunks = build_chunks(doc, tag_map)
        all_chunks.extend(chunks)

    print(f"🧩 Total chunks: {len(all_chunks)}")

    # 🚀 Store in Elasticsearch
    store_in_elasticsearch(all_chunks)

    print("✅ Data successfully stored in Elasticsearch")

# -----------------------------
# RUN
# -----------------------------
if __name__ == "__main__":
    run_pipeline()