import re

# -----------------------------
# LOAD FILE
# -----------------------------
def load_chunks(filename):
    chunks = []
    current_chunk = ""

    with open(filename, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for line in lines:
        if line.startswith("=" * 80):
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
            current_chunk = ""
        else:
            current_chunk += line

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks


# -----------------------------
# CLEAN TEXT (IMPORTANT 🔥)
# -----------------------------
def clean_for_similarity(text):
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s]', '', text)  # remove punctuation
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# -----------------------------
# SIMILARITY FUNCTION (IMPROVED)
# -----------------------------
def similarity(a, b):
    a = clean_for_similarity(a)
    b = clean_for_similarity(b)

    a_words = set(a.split())
    b_words = set(b.split())

    if not a_words or not b_words:
        return 0

    common = a_words.intersection(b_words)
    return len(common) / max(len(a_words), len(b_words))


# -----------------------------
# MAIN VALIDATION LOGIC
# -----------------------------
def validate_chunks_90():
    important = load_chunks("important_chunks.txt")
    not_important = load_chunks("not_important_chunks.txt")

    correct_chunks = []   # ✅ truly non-important
    wrong_chunks = []     # ❌ misclassified (duplicates)

    print(f"📄 Important: {len(important)}")
    print(f"📄 Not Important: {len(not_important)}")

    # -----------------------------
    # COMPARE
    # -----------------------------
    for non_chunk in not_important:
        is_wrong = False

        for imp_chunk in important:
            sim = similarity(non_chunk, imp_chunk)

            if sim >= 0.90:  # 🔥 90% threshold
                wrong_chunks.append((non_chunk, imp_chunk, sim))
                is_wrong = True
                break

        if not is_wrong:
            correct_chunks.append(non_chunk)

    # -----------------------------
    # ACCURACY CALCULATION (FIXED ✅)
    # -----------------------------
    total = len(not_important)

    wrong_count = len(wrong_chunks)
    correct_count = len(correct_chunks)

    accuracy = (correct_count / total) * 100 if total else 0

    print("\n🎯 FINAL RESULTS")
    print(f"✅ Correct Non-Important: {correct_count}")
    print(f"❌ Wrong (Duplicates): {wrong_count}")
    print(f"📊 Accuracy: {accuracy:.2f}%")

    # -----------------------------
    # SAVE FILES
    # -----------------------------

    # 1. IMPORTANT (unchanged)
    with open("validated_important.txt", "w", encoding="utf-8") as f:
        for i, chunk in enumerate(important):
            f.write("=" * 80 + "\n")
            f.write(f"IMPORTANT CHUNK {i}\n\n")
            f.write(chunk + "\n\n")

    # 2. CORRECT NON-IMPORTANT
    with open("correct_non_important_90.txt", "w", encoding="utf-8") as f:
        for i, chunk in enumerate(correct_chunks):
            f.write("=" * 80 + "\n")
            f.write(f"CORRECT NON-IMPORTANT {i}\n\n")
            f.write(chunk + "\n\n")

    # 3. WRONG (DUPLICATES)
    with open("wrong_duplicates_90.txt", "w", encoding="utf-8") as f:
        for i, (non, imp, sim) in enumerate(wrong_chunks):
            f.write("=" * 80 + "\n")
            f.write(f"WRONG CHUNK {i}\n")
            f.write(f"SIMILARITY: {sim:.2f}\n\n")

            f.write("❌ FROM NOT IMPORTANT:\n")
            f.write(non + "\n\n")

            f.write("✅ MATCHED IMPORTANT:\n")
            f.write(imp + "\n\n")

    print("\n📂 Files Generated:")
    print("✔ validated_important.txt")
    print("✔ correct_non_important_90.txt")
    print("✔ wrong_duplicates_90.txt")


# -----------------------------
# RUN
# -----------------------------
if __name__ == "__main__":
    validate_chunks_90()