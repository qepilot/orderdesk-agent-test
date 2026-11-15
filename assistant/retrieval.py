"""Module 3: retrieval over the knowledge base, written out in full so nothing is a black box.

    load_documents   Markdown files with a small header -> Document
    chunk_document   Document -> passages of a few hundred characters, each carrying its title
    BM25Index        keyword ranking (the formula search engines used for decades)
    VectorIndex      embedding ranking by cosine similarity, with a pluggable embedder
    Retriever        keyword, vector or hybrid (reciprocal rank fusion), returning one hit per document

There is no vector database here: the corpus is small, so vectors live in a Python list. The
ideas are the same at any size; a database only makes the nearest-neighbour search faster.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import httpx


@dataclass(frozen=True)
class Document:
    doc_id: str
    doc_type: str
    date: str
    title: str
    tags: str
    text: str


@dataclass(frozen=True)
class Chunk:
    doc_id: str
    position: int
    text: str


@dataclass(frozen=True)
class Hit:
    doc_id: str
    doc_type: str
    date: str
    title: str
    score: float
    snippet: str


def load_documents(folder: Path) -> list[Document]:
    documents = []
    for path in sorted(folder.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        header, _, body = raw.removeprefix("---\n").partition("\n---\n")
        meta = dict(line.split(": ", 1) for line in header.splitlines() if ": " in line)
        documents.append(Document(meta.get("id", path.stem), meta.get("type", "document"), meta.get("date", ""),
                                  meta.get("title", path.stem), meta.get("tags", ""), body.strip()))
    return documents


def chunk_document(document: Document, max_chars: int = 600) -> list[Chunk]:
    """Splits at blank lines and packs paragraphs into passages. Every passage starts with the title,
    so a passage found on its own still says what it is about."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", document.text) if p.strip() and not p.startswith("# ")]
    passages, current = [], ""
    for paragraph in paragraphs:
        if current and len(current) + len(paragraph) > max_chars:
            passages.append(current)
            current = ""
        current = f"{current}\n{paragraph}".strip()
    if current:
        passages.append(current)
    return [Chunk(document.doc_id, position, f"{document.title}. {passage}") for position, passage in enumerate(passages)]


# -- keyword search ------------------------------------------------------------------------------

STOPWORDS = frozenset("a an and are as at be but by for from had has have how in is it its of on or that the "
                      "their there this to was were what when which who why will with not no do does did".split())
_WORD = re.compile(r"[a-z0-9_]+")


def tokenize(text: str) -> list[str]:
    """Lowercase words without stopwords, with the plainest possible stemming (plural s, -ing, -ed)."""
    tokens = []
    for word in _WORD.findall(text.lower()):
        if word in STOPWORDS or len(word) < 2:
            continue
        for suffix in ("ing", "ed", "es", "s"):
            if word.endswith(suffix) and len(word) - len(suffix) >= 4:
                word = word[: -len(suffix)]
                break
        tokens.append(word)
    return tokens


class BM25Index:
    """Okapi BM25: a term counts more when it is rare in the corpus (IDF), counts less each extra time it
    appears in a passage (k1), and long passages are not favoured just for being long (b)."""

    def __init__(self, chunks: list[Chunk], k1: float = 1.5, b: float = 0.75):
        self.chunks, self.k1, self.b = chunks, k1, b
        self.term_counts = [Counter(tokenize(chunk.text)) for chunk in chunks]
        self.lengths = [sum(counts.values()) for counts in self.term_counts]
        self.average_length = sum(self.lengths) / max(len(chunks), 1)
        document_frequency = Counter(term for counts in self.term_counts for term in counts)
        self.idf = {term: math.log(1 + (len(chunks) - df + 0.5) / (df + 0.5)) for term, df in document_frequency.items()}

    def search(self, query: str, k: int = 5) -> list[tuple[int, float]]:
        terms = tokenize(query)
        scores = []
        for index, counts in enumerate(self.term_counts):
            score = 0.0
            for term in terms:
                frequency = counts.get(term, 0)
                if frequency:
                    norm = self.k1 * (1 - self.b + self.b * self.lengths[index] / self.average_length)
                    score += self.idf[term] * frequency * (self.k1 + 1) / (frequency + norm)
            if score > 0:
                scores.append((index, score))
        return sorted(scores, key=lambda item: -item[1])[:k]


# -- vector search --------------------------------------------------------------------------------


class Embedder(Protocol):
    name: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashedNgramEmbedder:
    """An offline stand-in for an embedding model. It turns a text into a vector by hashing its
    character 3- to 5-grams into a fixed number of buckets.

    It shows the mechanics of vector search (vectors, cosine similarity, top-k) and it tolerates
    spelling variants ("index", "indexes", "indexing"). It does NOT understand meaning: "slow" and
    "latency" share no characters, so they stay far apart. A real embedding model closes that gap.
    """

    name = "hashed-ngrams (offline stand-in)"

    def __init__(self, dimensions: int = 512):
        self.dimensions = dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(text) for text in texts]

    def _one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for word in tokenize(text):
            padded = f"^{word}$"
            for size in (3, 4, 5):
                for start in range(max(len(padded) - size + 1, 1)):
                    digest = hashlib.md5(padded[start:start + size].encode()).digest()
                    vector[int.from_bytes(digest[:4], "big") % self.dimensions] += 1.0
        return _unit(vector)


class ApiEmbedder:
    """A real embedding model behind the OpenAI-compatible POST {base_url}/embeddings endpoint.

    Configure EMBED_MODEL (and EMBED_BASE_URL / EMBED_API_KEY when they differ from the chat endpoint).
    """

    def __init__(self, model: str | None = None, base_url: str | None = None, api_key: str | None = None,
                 timeout: float = 60.0):
        self.name = model or os.environ["EMBED_MODEL"]
        self.base_url = (base_url or os.getenv("EMBED_BASE_URL") or os.getenv("LLM_BASE_URL")
                         or "https://openrouter.ai/api/v1").rstrip("/")
        self.api_key = api_key or os.getenv("EMBED_API_KEY") or os.getenv("LLM_API_KEY", "")
        self.timeout = timeout

    def embed(self, texts: list[str]) -> list[list[float]]:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        response = httpx.post(f"{self.base_url}/embeddings", json={"model": self.name, "input": texts},
                              headers=headers, timeout=self.timeout)
        response.raise_for_status()
        rows = sorted(response.json()["data"], key=lambda row: row["index"])
        return [_unit(row["embedding"]) for row in rows]


def embedder_from_env() -> Embedder:
    return ApiEmbedder() if os.getenv("EMBED_MODEL", "").strip() else HashedNgramEmbedder()


def _unit(vector: list[float]) -> list[float]:
    length = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / length for value in vector]


def cosine(left: list[float], right: list[float]) -> float:
    """For unit-length vectors the cosine similarity is just the dot product."""
    return sum(a * b for a, b in zip(left, right))


class VectorIndex:
    def __init__(self, chunks: list[Chunk], embedder: Embedder):
        self.chunks, self.embedder = chunks, embedder
        self.vectors = embedder.embed([chunk.text for chunk in chunks])

    def search(self, query: str, k: int = 5) -> list[tuple[int, float]]:
        query_vector = self.embedder.embed([query])[0]
        scores = [(index, cosine(query_vector, vector)) for index, vector in enumerate(self.vectors)]
        return sorted(scores, key=lambda item: -item[1])[:k]


# -- putting rankings together ------------------------------------------------------------------------


def reciprocal_rank_fusion(rankings: list[list[int]], constant: int = 60) -> list[tuple[int, float]]:
    """Merges ranked lists without comparing their scores (BM25 scores and cosines live on different
    scales). An item earns 1 / (constant + rank) from every list it appears in."""
    fused: dict[int, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            fused[item] = fused.get(item, 0.0) + 1.0 / (constant + rank)
    return sorted(fused.items(), key=lambda item: -item[1])


class Retriever:
    """mode: "keyword" (BM25), "vector" (embeddings) or "hybrid" (both, fused)."""

    def __init__(self, folder: Path, mode: str = "hybrid", embedder: Embedder | None = None, max_chars: int = 600):
        if mode not in ("keyword", "vector", "hybrid"):
            raise ValueError("mode must be keyword, vector or hybrid")
        self.mode = mode
        self.documents = {document.doc_id: document for document in load_documents(folder)}
        self.chunks = [chunk for document in self.documents.values() for chunk in chunk_document(document, max_chars)]
        self.bm25 = BM25Index(self.chunks)
        self.vectors = VectorIndex(self.chunks, embedder or HashedNgramEmbedder()) if mode != "keyword" else None

    def rank_chunks(self, query: str, depth: int = 20) -> list[tuple[int, float]]:
        if self.mode == "keyword":
            return self.bm25.search(query, depth)
        if self.mode == "vector":
            return self.vectors.search(query, depth)
        return reciprocal_rank_fusion([[index for index, _ in self.bm25.search(query, depth)],
                                       [index for index, _ in self.vectors.search(query, depth)]])

    def search(self, query: str, k: int = 4) -> list[Hit]:
        hits: dict[str, Hit] = {}
        for index, score in self.rank_chunks(query):
            chunk = self.chunks[index]
            if chunk.doc_id in hits:
                continue            # the best passage of a document represents it
            document = self.documents[chunk.doc_id]
            snippet = " ".join(chunk.text.split())
            hits[chunk.doc_id] = Hit(document.doc_id, document.doc_type, document.date, document.title, score,
                                     snippet if len(snippet) <= 320 else snippet[:317] + "...")
            if len(hits) == k:
                break
        return list(hits.values())

    def get(self, doc_id: str) -> Document | None:
        return self.documents.get(doc_id.strip())


def recall_at_k(retriever: Retriever, labelled: list[dict], k: int = 3) -> dict:
    """Share of queries for which at least one relevant document is in the top k, plus the misses."""
    found, misses = 0, []
    for case in labelled:
        returned = [hit.doc_id for hit in retriever.search(case["query"], k)]
        if set(returned) & set(case["relevant"]):
            found += 1
        else:
            misses.append({"query": case["query"], "wanted": case["relevant"], "got": returned})
    return {"recall": found / max(len(labelled), 1), "found": found, "total": len(labelled), "misses": misses}
