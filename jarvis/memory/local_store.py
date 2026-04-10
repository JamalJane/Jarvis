"""
LocalMemoryStore — Hybrid keyword + vector search over Jarvis's long-term memory.

Stores memories in two tiers:
  workspace/MEMORY.md          — evergreen facts (manually maintained)
  workspace/memory/daily/*.jsonl — daily agent-written log entries

Search pipeline: TF-IDF keyword → hash-based vector → merge → temporal decay → MMR rerank

Ported and adapted from the reference intelligence example.
"""
import json
import math
import re
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

WORKSPACE_DIR = Path(__file__).resolve().parent.parent.parent / "workspace"


class LocalMemoryStore:

    def __init__(self, workspace_dir: Optional[Path] = None) -> None:
        self.workspace_dir = workspace_dir or WORKSPACE_DIR
        self.memory_dir = self.workspace_dir / "memory" / "daily"
        self.memory_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # WRITE                                                                 #
    # ------------------------------------------------------------------ #

    def write_memory(self, content: str, category: str = "general") -> str:
        """Append an entry to today's daily JSONL file."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = self.memory_dir / f"{today}.jsonl"
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "category": category,
            "content": content,
        }
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            logger.info(f"[memory] wrote [{category}] {content[:60]}")
            return f"Memory saved ({category})"
        except Exception as exc:
            logger.warning(f"[memory] write failed: {exc}")
            return f"Error writing memory: {exc}"

    def load_evergreen(self) -> str:
        """Load the MEMORY.md evergreen facts file."""
        path = self.workspace_dir / "MEMORY.md"
        if not path.is_file():
            return ""
        try:
            return path.read_text(encoding="utf-8").strip()
        except Exception:
            return ""

    # ------------------------------------------------------------------ #
    # INTERNAL: chunk loader                                                #
    # ------------------------------------------------------------------ #

    def _load_all_chunks(self) -> List[Dict[str, str]]:
        chunks: List[Dict[str, str]] = []
        evergreen = self.load_evergreen()
        if evergreen:
            for para in evergreen.split("\n\n"):
                para = para.strip()
                if para:
                    chunks.append({"path": "MEMORY.md", "text": para})

        if self.memory_dir.is_dir():
            for jf in sorted(self.memory_dir.glob("*.jsonl")):
                try:
                    for line in jf.read_text(encoding="utf-8").splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        entry = json.loads(line)
                        text = entry.get("content", "")
                        if text:
                            cat = entry.get("category", "")
                            label = f"{jf.name} [{cat}]" if cat else jf.name
                            chunks.append({"path": label, "text": text})
                except Exception:
                    continue
        return chunks

    # ------------------------------------------------------------------ #
    # SEARCH: TF-IDF keyword channel                                        #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        tokens = re.findall(r"[a-z0-9]+", text.lower())
        return [t for t in tokens if len(t) > 1]

    def _keyword_search(self, query: str, chunks: List[Dict], top_k: int = 10) -> List[Dict]:
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []
        chunk_tokens = [self._tokenize(c["text"]) for c in chunks]
        n = len(chunks)
        df: Dict[str, int] = {}
        for tokens in chunk_tokens:
            for t in set(tokens):
                df[t] = df.get(t, 0) + 1

        def tfidf(tokens: List[str]) -> Dict[str, float]:
            tf: Dict[str, int] = {}
            for t in tokens:
                tf[t] = tf.get(t, 0) + 1
            return {t: c * (math.log((n + 1) / (df.get(t, 0) + 1)) + 1) for t, c in tf.items()}

        def cosine(a: Dict[str, float], b: Dict[str, float]) -> float:
            common = set(a) & set(b)
            if not common:
                return 0.0
            dot = sum(a[k] * b[k] for k in common)
            na = math.sqrt(sum(v * v for v in a.values()))
            nb = math.sqrt(sum(v * v for v in b.values()))
            return dot / (na * nb) if na and nb else 0.0

        qvec = tfidf(query_tokens)
        scored = []
        for i, tokens in enumerate(chunk_tokens):
            score = cosine(qvec, tfidf(tokens)) if tokens else 0.0
            if score > 0:
                scored.append({"chunk": chunks[i], "score": score})
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    # ------------------------------------------------------------------ #
    # SEARCH: Hash-based vector channel (no external API)                   #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _hash_vector(text: str, dim: int = 64) -> List[float]:
        tokens = LocalMemoryStore._tokenize(text)
        vec = [0.0] * dim
        for token in tokens:
            h = hash(token)
            for i in range(dim):
                bit = (h >> (i % 62)) & 1
                vec[i] += 1.0 if bit else -1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    @staticmethod
    def _vector_cosine(a: List[float], b: List[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(x * x for x in b))
        return dot / (na * nb) if na and nb else 0.0

    def _vector_search(self, query: str, chunks: List[Dict], top_k: int = 10) -> List[Dict]:
        q_vec = self._hash_vector(query)
        scored = []
        for chunk in chunks:
            score = self._vector_cosine(q_vec, self._hash_vector(chunk["text"]))
            if score > 0:
                scored.append({"chunk": chunk, "score": score})
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    # ------------------------------------------------------------------ #
    # MERGE + DECAY + MMR                                                   #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _merge(vector_results: List[Dict], keyword_results: List[Dict],
               v_weight: float = 0.7, k_weight: float = 0.3) -> List[Dict]:
        merged: Dict[str, Dict] = {}
        for r in vector_results:
            key = r["chunk"]["text"][:100]
            merged[key] = {"chunk": r["chunk"], "score": r["score"] * v_weight}
        for r in keyword_results:
            key = r["chunk"]["text"][:100]
            if key in merged:
                merged[key]["score"] += r["score"] * k_weight
            else:
                merged[key] = {"chunk": r["chunk"], "score": r["score"] * k_weight}
        result = list(merged.values())
        result.sort(key=lambda x: x["score"], reverse=True)
        return result

    @staticmethod
    def _temporal_decay(results: List[Dict], decay_rate: float = 0.01) -> List[Dict]:
        now = datetime.now(timezone.utc)
        for r in results:
            path = r["chunk"].get("path", "")
            age_days = 0.0
            m = re.search(r"(\d{4}-\d{2}-\d{2})", path)
            if m:
                try:
                    chunk_date = datetime.strptime(m.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    age_days = (now - chunk_date).total_seconds() / 86400.0
                except ValueError:
                    pass
            r["score"] *= math.exp(-decay_rate * age_days)
        return results

    @staticmethod
    def _mmr_rerank(results: List[Dict], lambda_param: float = 0.7) -> List[Dict]:
        """Maximal Marginal Relevance — balances relevance with diversity."""
        if len(results) <= 1:
            return results
        tokenized = [LocalMemoryStore._tokenize(r["chunk"]["text"]) for r in results]
        selected: List[int] = []
        remaining = list(range(len(results)))
        reranked: List[Dict] = []
        while remaining:
            best_idx, best_mmr = -1, float("-inf")
            for idx in remaining:
                relevance = results[idx]["score"]
                max_sim = 0.0
                for sel in selected:
                    sa, sb = set(tokenized[idx]), set(tokenized[sel])
                    sim = len(sa & sb) / len(sa | sb) if (sa | sb) else 0.0
                    max_sim = max(max_sim, sim)
                mmr = lambda_param * relevance - (1 - lambda_param) * max_sim
                if mmr > best_mmr:
                    best_mmr, best_idx = mmr, idx
            selected.append(best_idx)
            remaining.remove(best_idx)
            reranked.append(results[best_idx])
        return reranked

    # ------------------------------------------------------------------ #
    # PUBLIC: hybrid search                                                 #
    # ------------------------------------------------------------------ #

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Full hybrid search: keyword + vector → merge → decay → MMR → top_k."""
        chunks = self._load_all_chunks()
        if not chunks:
            return []
        keyword_results = self._keyword_search(query, chunks, top_k=10)
        vector_results  = self._vector_search(query, chunks, top_k=10)
        merged  = self._merge(vector_results, keyword_results)
        decayed = self._temporal_decay(merged)
        reranked = self._mmr_rerank(decayed)
        output = []
        for r in reranked[:top_k]:
            snippet = r["chunk"]["text"]
            if len(snippet) > 200:
                snippet = snippet[:200] + "..."
            output.append({
                "path": r["chunk"]["path"],
                "score": round(r["score"], 4),
                "snippet": snippet,
            })
        return output

    def get_stats(self) -> Dict[str, Any]:
        evergreen = self.load_evergreen()
        daily_files = list(self.memory_dir.glob("*.jsonl")) if self.memory_dir.is_dir() else []
        total_entries = 0
        for f in daily_files:
            try:
                total_entries += sum(
                    1 for line in f.read_text(encoding="utf-8").splitlines() if line.strip()
                )
            except Exception:
                pass
        return {
            "evergreen_chars": len(evergreen),
            "daily_files": len(daily_files),
            "daily_entries": total_entries,
        }
