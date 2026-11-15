from pymongo import MongoClient
import os
import hashlib
import re
from dotenv import load_dotenv

# -----------------------------
# CONFIG
# -----------------------------
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = "docs_backend"

mongo_client = MongoClient(MONGO_URI)
db = mongo_client[DB_NAME]
docs_col = db["docs"]

# -----------------------------
# CLEAN TEXT
# -----------------------------
def clean_text(text):
    if not text:
        return ""

    text = re.sub(r'<[^>]+>', ' ', text)
    text = text.replace("&nbsp;", " ")
    text = text.replace("&amp;", "&")
    text = re.sub(r'\s+', ' ', text)

    return text.strip()

# -----------------------------
# SPLIT BY HEADINGS
# -----------------------------
def split_by_headings(text):
    parts = re.split(r'(\n\s*(?:##|#|\d+\.)\s+)', text)

    sections = []
    current = ""

    for part in parts:
        if re.match(r'\n\s*(?:##|#|\d+\.)\s+', part):
            if current:
                sections.append(current.strip())
            current = part.strip()
        else:
            current += " " + part

    if current:
        sections.append(current.strip())

    return sections

# -----------------------------
# SEMANTIC CHUNKING
# -----------------------------
def semantic_chunk(section, max_words=120):
    sentences = re.split(r'(?<=[.!?]) +', section)

    chunks = []
    current = []

    for sentence in sentences:
        words = sentence.split()

        if len(" ".join(current).split()) + len(words) > max_words:
            if current:
                chunks.append(" ".join(current))
                current = []

        current.append(sentence)

    if current:
        chunks.append(" ".join(current))

    return chunks

# -----------------------------
# HYBRID CHUNKING
# -----------------------------
def hybrid_chunking(text):
    final_chunks = []

    sections = split_by_headings(text)

    for section in sections:
        chunks = semantic_chunk(section)
        final_chunks.extend(chunks)

    return final_chunks

# -----------------------------
# HASH FUNCTION
# -----------------------------
def hash_chunk(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

# -----------------------------
# CLASSIFICATION LOGIC
# -----------------------------
def is_storytelling(chunk):
    text = chunk.lower()

    patterns = [
        "i ", "we ", "my ", "our ",
        "once", "a while ago", "i remember",
        "i was", "we were", "in my experience",
        "let me tell you", "trust me",
        "story", "journey", "experience",
        "one day", "suddenly", "then"
    ]

    return any(p in text for p in patterns)


def is_definition(chunk):
    text = chunk.lower()

    patterns = [
        "is a", "is an", "refers to",
        "defined as", "means",
        "is the process of",
        "can be defined as"
    ]

    return any(p in text for p in patterns)


def is_technical(chunk):
    text = chunk.lower()

    keywords = [
        "api", "server", "client", "database",
        "protocol", "http", "https",
        "dns", "domain", "ip address",
        "backend", "frontend",
        "authentication", "authorization",
        "json", "request", "response",
        "latency", "throughput"
    ]

    return any(k in text for k in keywords)


def is_important(chunk):
    words = len(chunk.split())

    if words < 20:
        return False

    if is_storytelling(chunk):
        return False

    if is_definition(chunk):
        return True

    if is_technical(chunk):
        return True

    return False

# -----------------------------
# SAVE FILES (UPDATED)
# -----------------------------
def save_files(important, non_important, hashed):

    # IMPORTANT FILE (WITH HASH)
    with open("important_chunks.txt", "w", encoding="utf-8") as f:
        for i, (chunk, h) in enumerate(hashed):
            f.write("=" * 80 + "\n")
            f.write(f"IMPORTANT CHUNK {i}\n")
            f.write(f"HASH: {h}\n\n")
            f.write(chunk + "\n\n")

    # NOT IMPORTANT FILE (WITH HASH)
    with open("not_important_chunks.txt", "w", encoding="utf-8") as f:
        for i, chunk in enumerate(non_important):
            h = hash_chunk(chunk)
            f.write("=" * 80 + "\n")
            f.write(f"NOT IMPORTANT CHUNK {i}\n")
            f.write(f"HASH: {h}\n\n")
            f.write(chunk + "\n\n")

    # HASHED IMPORTANT FILE (UNCHANGED)
    with open("important_chunks_hashed.txt", "w", encoding="utf-8") as f:
        for i, (chunk, h) in enumerate(hashed):
            f.write("=" * 80 + "\n")
            f.write(f"CHUNK {i}\n")
            f.write(f"HASH: {h}\n\n")
            f.write(chunk + "\n\n")

# -----------------------------
# MAIN PIPELINE
# -----------------------------
def run_pipeline():
    docs = list(docs_col.find({"isdelete": {"$ne": True}}))

    print(f"📄 Total docs: {len(docs)}")

    important_chunks = []
    non_important_chunks = []
    hashed_chunks = []

    seen_hashes = set()

    for doc in docs:
        raw_text = doc.get("content", "")

        if not raw_text:
            continue

        cleaned = clean_text(raw_text)
        chunks = hybrid_chunking(cleaned)

        for chunk in chunks:
            h = hash_chunk(chunk)

            if h in seen_hashes:
                continue

            seen_hashes.add(h)

            if is_important(chunk):
                important_chunks.append(chunk)
                hashed_chunks.append((chunk, h))
            else:
                non_important_chunks.append(chunk)

    print(f"✅ Important: {len(important_chunks)}")
    print(f"❌ Not Important: {len(non_important_chunks)}")

    save_files(important_chunks, non_important_chunks, hashed_chunks)

    print("\n🎯 Files Generated:")
    print("✔ important_chunks.txt (WITH HASH)")
    print("✔ not_important_chunks.txt (WITH HASH)")
    print("✔ important_chunks_hashed.txt")


# -----------------------------
# RUN
# -----------------------------
if __name__ == "__main__":
    run_pipeline()