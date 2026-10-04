"""Pure-Python TF-IDF retrieval over the policy corpus.

No external ML dependency: policy markdown files are chunked by section, each
section gets a bag-of-words TF-IDF vector, and queries are scored by cosine
similarity. Small corpus (a few dozen sections) makes this entirely adequate
and keeps the project installable with just fastapi+uvicorn.
"""
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

POLICY_DIR = Path(__file__).parent.parent / "policies"

SECTION_RE = re.compile(r"^##\s+([A-Z]+(?:-[A-Z0-9]+)*)\.\s+(.+)$", re.MULTILINE)
WORD_RE = re.compile(r"[a-z0-9]+")

STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "for", "on", "is", "are",
    "be", "must", "with", "as", "by", "this", "that", "within", "at", "any",
    "all", "must", "shall", "which", "from", "or", "such", "per", "will",
    "into", "its", "it", "has", "have", "been", "may", "not", "than",
}


def tokenize(text: str) -> list[str]:
    return [w for w in WORD_RE.findall(text.lower()) if w not in STOPWORDS and len(w) > 1]


@dataclass
class PolicySection:
    section_id: str
    title: str
    text: str
    doc_name: str


class PolicyIndex:
    def __init__(self, policy_dir: Path = POLICY_DIR):
        self.sections: list[PolicySection] = []
        self._load(policy_dir)
        self._build_index()

    def _load(self, policy_dir: Path):
        for path in sorted(policy_dir.glob("*.md")):
            content = path.read_text()
            matches = list(SECTION_RE.finditer(content))
            for i, m in enumerate(matches):
                section_id, title = m.group(1), m.group(2)
                start = m.end()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
                body = content[start:end].strip()
                self.sections.append(PolicySection(
                    section_id=section_id, title=title, text=body, doc_name=path.stem,
                ))

    def _build_index(self):
        self._doc_tokens = [tokenize(f"{s.title} {s.text}") for s in self.sections]
        self._df: Counter = Counter()
        for tokens in self._doc_tokens:
            for term in set(tokens):
                self._df[term] += 1
        n_docs = max(len(self._doc_tokens), 1)
        self._idf = {term: math.log((n_docs + 1) / (df + 1)) + 1 for term, df in self._df.items()}
        self._doc_vectors = [self._vectorize(tokens) for tokens in self._doc_tokens]

    def _vectorize(self, tokens: list[str]) -> dict[str, float]:
        tf = Counter(tokens)
        vec = {}
        for term, count in tf.items():
            idf = self._idf.get(term, math.log(len(self._doc_tokens) + 1) + 1)
            vec[term] = count * idf
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return {k: v / norm for k, v in vec.items()}

    @staticmethod
    def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
        if len(a) > len(b):
            a, b = b, a
        return sum(v * b.get(k, 0.0) for k, v in a.items())

    def search(self, query: str, top_k: int = 3, section_ids: list[str] | None = None):
        query_vec = self._vectorize(tokenize(query))
        scored = []
        for section, doc_vec in zip(self.sections, self._doc_vectors):
            if section_ids and section.section_id not in section_ids:
                continue
            score = self._cosine(query_vec, doc_vec)
            if score > 0:
                scored.append((score, section))
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[:top_k]

    def get(self, section_id: str) -> PolicySection | None:
        for s in self.sections:
            if s.section_id == section_id:
                return s
        return None

    def get_many(self, section_ids: list[str]) -> list[PolicySection]:
        found = []
        for sid in section_ids:
            s = self.get(sid)
            if s:
                found.append(s)
        return found
