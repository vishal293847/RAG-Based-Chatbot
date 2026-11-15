from elasticsearch import Elasticsearch, helpers
from sentence_transformers import SentenceTransformer
import os
from dotenv import load_dotenv

# -----------------------------
# CONFIG
# -----------------------------
load_dotenv()

ES_HOST = os.getenv("ES_HOST")
ES_USER = os.getenv("ES_USER")
ES_PASS = os.getenv("ES_PASS")

INDEX_NAME = "mxy-chatbot_v2"

MODEL_NAME = "all-MiniLM-L6-v2"  # 384 dims

# -----------------------------
# CONNECT
# -----------------------------
es = Elasticsearch(
    ES_HOST,
    basic_auth=(ES_USER, ES_PASS)
)

model = SentenceTransformer(MODEL_NAME)

# -----------------------------
# FETCH DATA (NO EMBEDDINGS)
# -----------------------------
def fetch_chunks_without_embeddings():
    query = {
        "query": {
            "bool": {
                "must_not": [
                    {"exists": {"field": "embedding"}}
                ]
            }
        }
    }

    page = es.search(index=INDEX_NAME, body=query, scroll="2m", size=1000)
    sid = page["_scroll_id"]
    hits = page["hits"]["hits"]

    all_hits = hits.copy()

    while True:
        page = es.scroll(scroll_id=sid, scroll="2m")
        hits = page["hits"]["hits"]
        if not hits:
            break
        all_hits.extend(hits)

    print(f"📦 Chunks without embeddings: {len(all_hits)}")
    return all_hits

# -----------------------------
# CREATE EMBEDDINGS
# -----------------------------
def create_embeddings(batch_size=64):
    hits = fetch_chunks_without_embeddings()

    if not hits:
        print("✅ All chunks already have embeddings")
        return

    actions = []
    success = 0

    for i in range(0, len(hits), batch_size):
        batch = hits[i:i + batch_size]

        texts = [
            h["_source"].get("content", "")
            for h in batch
        ]

        try:
            embeddings = model.encode(
                texts,
                batch_size=batch_size,
                convert_to_numpy=True,
                normalize_embeddings=True
            )

            for j, emb in enumerate(embeddings):
                actions.append({
                    "_op_type": "update",
                    "_index": INDEX_NAME,
                    "_id": batch[j]["_id"],
                    "doc": {
                        "embedding": emb.tolist()
                    }
                })
                success += 1

            print(f"✅ Batch {(i // batch_size) + 1} done")

        except Exception as e:
            print(f"❌ Error in batch {(i // batch_size) + 1}: {e}")

        # Bulk update
        if len(actions) >= 500:
            helpers.bulk(es, actions)
            actions = []

    # Final flush
    if actions:
        helpers.bulk(es, actions)

    print("\n🎯 FINAL RESULT:")
    print(f"✅ Embedded: {success}/{len(hits)}")

# -----------------------------
# RUN
# -----------------------------
if __name__ == "__main__":
    print("🚀 Adding embeddings to Elasticsearch...")
    create_embeddings(batch_size=64)