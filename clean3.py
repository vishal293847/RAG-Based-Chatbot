from pymongo import MongoClient
import ollama
import os
import hashlib
import re
import json
import time
import requests
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
tags_col = db["tags"]
categories_col = db["categories"]


OLLAMA_MODEL = "mistral"   # you can change to llama3

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
# BASIC FALLBACK CHUNKING
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
# 🔥 OLLAMA SEMANTIC CHUNKING
# -----------------------------
def ollama_semantic_chunk(section):
    prompt = f"""
You are a smart text chunking assistant.

Split the text into meaningful semantic chunks.

Rules:
- Each chunk = one idea
- Separate definitions, features, and explanations
- Remove storytelling / fluff
- Keep chunks clean and useful
- Return ONLY JSON array

Text:
{section}
"""

    try:
        response = ollama.chat(
           
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False
            },
            timeout=60
        )

        result = response.json()["response"]

        chunks = json.loads(result)

        return [c.strip() for c in chunks if len(c.strip()) > 20]

    except Exception as e:
        print("⚠️ Ollama failed, fallback used:", e)
        return []

# -----------------------------
# HYBRID CHUNKING (OLLAMA + FALLBACK)
# -----------------------------
def hybrid_chunking(text):
    final_chunks = []
    sections = split_by_headings(text)

    for section in sections:

        # skip very small sections
        if len(section.split()) < 30:
            final_chunks.append(section)
            continue

        chunks = ollama_semantic_chunk(section)

        if not chunks:
            chunks = semantic_chunk(section)

        final_chunks.extend(chunks)

        time.sleep(0.5)  # prevent overload

    return final_chunks

# -----------------------------
# HASH
# -----------------------------
def hash_chunk(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

# -----------------------------
# MARKETXY FILTER
# -----------------------------
def get_marketxy_tag_ids():
    tags = tags_col.find({
        "name": {"$regex": "marketxy", "$options": "i"}
    })
    return [tag["_id"] for tag in tags]


def get_docs_by_tags(tag_ids):
    return list(docs_col.find({
        "tags": {"$in": tag_ids},
        "isdelete": {"$ne": True}
    }))


def get_categories_by_name():
    return list(categories_col.find({
        "name": {"$regex": "marketxy", "$options": "i"},
        "isdelete": {"$ne": True}
    }))


def get_docs_from_categories(categories):
    ids = set()

    for cat in categories:
        for doc_id in cat.get("docs", []):
            ids.add(doc_id)

    return list(docs_col.find({
        "_id": {"$in": list(ids)},
        "isdelete": {"$ne": True}
    }))


def get_docs_by_content():
    return list(docs_col.find({
        "content": {"$regex": "marketxy|mxy", "$options": "i"},
        "isdelete": {"$ne": True}
    }))

# -----------------------------
# LINK EXTRACTION
# -----------------------------
def extract_links_with_headings(text):
    results = []

    sections = split_by_headings(text)

    for section in sections:
        heading = section.split("\n")[0][:100]
        links = re.findall(r'https?://[^\s]+', section)

        for link in links:
            results.append((heading.strip(), link.strip()))

    return results

# -----------------------------
# CLASSIFICATION
# -----------------------------
def has_feature_content(chunk):
    return any(p in chunk.lower() for p in [
        "added","introduced","new feature","feature","enhanced"
    ])

def is_release_notes(chunk):
    return any(p in chunk.lower() for p in [
        "release note","changelog","what's new"
    ])

def is_storytelling(chunk):
    return any(p in chunk.lower() for p in [
        "i ","we ","my ","our ","experience"
    ])

def is_definition(chunk):
    if " is " in chunk.lower():
        return True
    return False

def is_technical(chunk):
    return any(k in chunk.lower() for k in [
        "api","server","database","http","backend"
    ])

def is_informational(chunk):
    return any(p in chunk.lower() for p in [
        "used for","how it works","process"
    ])

def is_noise(chunk):
    return any(p in chunk.lower() for p in [
        "click here","subscribe","welcome"
    ])

def is_important(chunk):
    if is_release_notes(chunk):
        return has_feature_content(chunk)
    if is_definition(chunk):
        return True
    if is_storytelling(chunk):
        return False
    if is_noise(chunk):
        return False
    if is_technical(chunk):
        return True
    if is_informational(chunk):
        return True
    return len(chunk.split()) > 40

# -----------------------------
# SAVE FILES
# -----------------------------
def save_files(important, non_important, hashed, links):

    with open("important_chunks.txt", "w", encoding="utf-8") as f:
        for i, c in enumerate(important):
            f.write("="*80+"\nIMPORTANT "+str(i)+"\n\n"+c+"\n\n")

    with open("not_important_chunks.txt", "w", encoding="utf-8") as f:
        for i, c in enumerate(non_important):
            f.write("="*80+"\nNOT IMPORTANT "+str(i)+"\n\n"+c+"\n\n")

    with open("important_chunks_hashed.txt", "w", encoding="utf-8") as f:
        for i, (c,h) in enumerate(hashed):
            f.write("="*80+"\nHASH: "+h+"\n\n"+c+"\n\n")

    with open("links_with_headings.txt", "w", encoding="utf-8") as f:
        for i, (h,l) in enumerate(links):
            f.write("="*80+"\nHEADING: "+h+"\nURL: "+l+"\n\n")

# -----------------------------
# MAIN PIPELINE
# -----------------------------
def run_pipeline():

    print("🚀 Fetching MarketXY Data...")

    tag_ids = get_marketxy_tag_ids()
    docs1 = get_docs_by_tags(tag_ids)

    cats = get_categories_by_name()
    docs2 = get_docs_from_categories(cats)

    docs3 = get_docs_by_content()

    all_docs = {d["_id"]: d for d in (docs1 + docs2 + docs3)}.values()

    print(f"📄 Total Docs: {len(all_docs)}")

    important, non_important, hashed = [], [], []
    links = []
    seen = set()

    for doc in all_docs:
        cleaned = clean_text(doc.get("content",""))

        links.extend(extract_links_with_headings(cleaned))

        chunks = hybrid_chunking(cleaned)

        for chunk in chunks:
            h = hash_chunk(chunk)

            if h in seen:
                continue
            seen.add(h)

            if is_important(chunk):
                important.append(chunk)
                hashed.append((chunk,h))
            else:
                non_important.append(chunk)

    print("✅ Important:", len(important))
    print("❌ Not Important:", len(non_important))

    save_files(important, non_important, hashed, links)

    print("🎯 Files Generated Successfully")

# -----------------------------
# RUN
# -----------------------------
if __name__ == "__main__":
    run_pipeline()