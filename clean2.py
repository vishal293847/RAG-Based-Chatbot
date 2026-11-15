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
# 🔥 EXTRACT LINKS WITH HEADINGS
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
# CLASSIFICATION LOGIC
# -----------------------------
def has_feature_content(chunk):
    text = chunk.lower()

    patterns = [
        "added", "introduced", "new feature",
        "now supports", "support for",
        "we added", "we introduced",
        "feature", "enhancement",
        "improved performance",
        "new capability", "new functionality",
        "upgrade", "enhanced"
    ]

    return any(p in text for p in patterns)


def is_release_notes(chunk):
    text = chunk.lower()

    patterns = [
        "release note", "release notes",
        "changelog", "version update",
        "version history", "new features",
        "bug fixes", "improvements",
        "fixed issues", "patch notes",
        "what's new", "whats new",
        "update notes", "release update"
    ]

    return any(p in text for p in patterns)


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
    text = chunk.lower().strip()

    patterns = [
        "is a", "is an", "refers to",
        "defined as", "means",
        "can be defined as",
        "is the process of",
        "is used to",
        "is responsible for",
        "it's a", "it is a"
    ]

    if any(p in text for p in patterns):
        return True

    if "-" in chunk:
        parts = chunk.split("-", 1)

        if len(parts) == 2:
            left = parts[0].strip()
            right = parts[1].strip()

            if len(left.split()) <= 6 and len(right.split()) > 8:
                return True

    return False


def is_technical(chunk):
    text = chunk.lower()

    keywords = [
        "api", "server", "client", "database",
        "protocol", "http", "https",
        "dns", "domain", "ip address",
        "backend", "frontend",
        "authentication", "authorization",
        "json", "request", "response",
        "latency", "throughput",
        "scalability", "performance",
        "architecture", "microservices",
        "cloud", "aws", "gcp", "azure",
        "docker", "kubernetes",
        "cache", "queue", "pipeline"
    ]

    return any(k in text for k in keywords)


def is_informational(chunk):
    text = chunk.lower()

    patterns = [
        "used for", "helps to", "allows you to",
        "important to", "key idea", "main purpose",
        "advantage", "benefit", "why",
        "how it works", "working of",
        "process of", "steps", "method",
        "approach", "technique"
    ]

    return any(p in text for p in patterns)


def is_noise(chunk):
    text = chunk.lower()

    patterns = [
        "click here", "read more", "subscribe",
        "follow us", "lorem ipsum",
        "welcome", "introduction", "overview"
    ]

    return any(p in text for p in patterns)


def is_important(chunk):
    words = len(chunk.split())

    if is_release_notes(chunk):
        if has_feature_content(chunk):
            return True
        else:
            return False

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

    if words > 40:
        return True

    return False


# -----------------------------
# SAVE FILES
# -----------------------------
def save_files(important, non_important, hashed, links_data):

    with open("important_chunks.txt", "w", encoding="utf-8") as f:
        for i, chunk in enumerate(important):
            f.write("=" * 80 + "\n")
            f.write(f"IMPORTANT CHUNK {i}\n\n")
            f.write(chunk + "\n\n")

    with open("not_important_chunks.txt", "w", encoding="utf-8") as f:
        for i, chunk in enumerate(non_important):
            f.write("=" * 80 + "\n")
            f.write(f"NOT IMPORTANT CHUNK {i}\n\n")
            f.write(chunk + "\n\n")

    with open("important_chunks_hashed.txt", "w", encoding="utf-8") as f:
        for i, (chunk, h) in enumerate(hashed):
            f.write("=" * 80 + "\n")
            f.write(f"CHUNK {i}\n")
            f.write(f"HASH: {h}\n\n")
            f.write(chunk + "\n\n")

    # 🔥 NEW FILE
    with open("links_with_headings.txt", "w", encoding="utf-8") as f:
        for i, (heading, link) in enumerate(links_data):
            f.write("=" * 80 + "\n")
            f.write(f"LINK {i}\n\n")
            f.write(f"HEADING: {heading}\n")
            f.write(f"URL: {link}\n\n")


# -----------------------------
# MAIN PIPELINE
# -----------------------------
def run_pipeline():
    docs = list(docs_col.find({"isdelete": {"$ne": True}}))

    print(f"📄 Total docs: {len(docs)}")

    important_chunks = []
    non_important_chunks = []
    hashed_chunks = []
    all_links = []

    seen_hashes = set()

    for doc in docs:
        raw_text = doc.get("content", "")

        if not raw_text:
            continue

        cleaned = clean_text(raw_text)

        # 🔥 Extract links
        links = extract_links_with_headings(cleaned)
        all_links.extend(links)

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
    print(f"🔗 Links Extracted: {len(all_links)}")

    save_files(important_chunks, non_important_chunks, hashed_chunks, all_links)

    print("\n🎯 Files Generated:")
    print("✔ important_chunks.txt")
    print("✔ not_important_chunks.txt")
    print("✔ important_chunks_hashed.txt")
    print("✔ links_with_headings.txt")


# -----------------------------
# RUN
# -----------------------------
if __name__ == "__main__":
    run_pipeline()