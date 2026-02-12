from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.utils import embedding_functions

"""
EXACT-ONLY Retriever

Policy:
- EXACT iff menu_norm matches chromadb.metadata["menu"] OR one of chromadb.metadata["variants"] (whitespace-normalized, csv/list)
- No jamo / no rerank / no thresholds
- Variants are treated as aliases that map to the canonical menu
"""

# --------- ENV routing (keep project conventions) ----------
ENV_CHROMA_DIR = "MENU_ASSISTANT_CHROMA_DIR"
ENV_CHROMA_S3_PREFIX = "MENU_ASSISTANT_CHROMA_S3_PREFIX"
ENV_COLLECTION = "MENU_ASSISTANT_COLLECTION"
ENV_EMBED_MODEL = "MENU_ASSISTANT_EMBED_MODEL"

DEFAULT_COLLECTION = "menu_index"
DEFAULT_EMBED_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

_WS_RE = re.compile(r"\s+")


def _norm_ws(s: str) -> str:
    s = (s or "").strip()
    return _WS_RE.sub(" ", s)


def _split_csv_like(v: Any) -> List[str]:
    if v is None:
        return []
    if isinstance(v, (list, tuple, set)):
        out: List[str] = []
        for x in v:
            xs = _norm_ws(str(x))
            if xs:
                out.append(xs)
        return out
    parts = [p.strip() for p in str(v).split(",")]
    return [p for p in parts if p]


def _parse_s3_uri(uri: str) -> Tuple[str, str]:
    if not uri.startswith("s3://"):
        raise ValueError(f"invalid s3 uri: {uri}")
    parts = uri[5:].split("/", 1)
    bucket = parts[0]
    prefix = parts[1] if len(parts) > 1 else ""
    return bucket, prefix


def _download_s3_prefix(uri: str, dest_dir: Path) -> None:
    # Lazy import to avoid hard dependency if not used
    import boto3

    bucket, prefix = _parse_s3_uri(uri)
    client = boto3.client("s3")
    dest_dir.mkdir(parents=True, exist_ok=True)

    continuation = None
    while True:
        kwargs = {"Bucket": bucket, "Prefix": prefix}
        if continuation:
            kwargs["ContinuationToken"] = continuation
        resp = client.list_objects_v2(**kwargs)
        for obj in resp.get("Contents", []):
            key = obj.get("Key", "")
            if key.endswith("/"):
                continue
            rel = key[len(prefix):] if key.startswith(prefix) else key
            rel = rel.lstrip("/")
            out_path = dest_dir / rel
            out_path.parent.mkdir(parents=True, exist_ok=True)
            client.download_file(bucket, key, str(out_path))
        if not resp.get("IsTruncated"):
            break
        continuation = resp.get("NextContinuationToken")


def _to_similarity(distance: Optional[float]) -> float:
    """Chroma distance -> similarity in [0,1] for cosine distance (1 - distance)."""
    if distance is None:
        return 0.0
    try:
        d = float(distance)
    except Exception:
        return 0.0
    return 1.0 - d


def _parse_metadata(md: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "menu": _norm_space(str(md.get("menu", ""))),
        "variants": _split_csv(md.get("variants", "")),
        "ingredients_ko": _split_csv(md.get("ingredients_ko", "")),
        "alg_tags": _split_csv(md.get("alg_tags", "")),
        "source": _norm_space(str(md.get("source", ""))),
    }


# ==============================
# JAMO SIMILARITY (typo-robust)
# ==============================
_SBASE = 0xAC00
_LBASE = 0x1100
_VBASE = 0x1161
_TBASE = 0x11A7
_LCOUNT = 19
_VCOUNT = 21
_TCOUNT = 28
_NCOUNT = _VCOUNT * _TCOUNT
_SCOUNT = _LCOUNT * _NCOUNT


def _hangul_to_jamo(s: str) -> str:
    out: List[str] = []
    for ch in s:
        code = ord(ch)
        if _SBASE <= code < (_SBASE + _SCOUNT):
            sindex = code - _SBASE
            l = _LBASE + (sindex // _NCOUNT)
            v = _VBASE + ((sindex % _NCOUNT) // _TCOUNT)
            t = _TBASE + (sindex % _TCOUNT)
            out.append(chr(l))
            out.append(chr(v))
            if t != _TBASE:
                out.append(chr(t))
        else:
            out.append(ch)
    return "".join(out)


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            ins = cur[j - 1] + 1
            dele = prev[j] + 1
            sub = prev[j - 1] + (0 if ca == cb else 1)
            cur.append(min(ins, dele, sub))
        prev = cur
    return prev[-1]


def jamo_similarity(a: str, b: str) -> float:
    a = _norm_space(a)
    b = _norm_space(b)
    if not a or not b:
        return 0.0
    ja = _hangul_to_jamo(a)
    jb = _hangul_to_jamo(b)
    dist = _levenshtein(ja, jb)
    denom = max(len(ja), len(jb), 1)
    return float(max(0.0, 1.0 - (dist / denom)))


# ==============================
# DATA STRUCTURES
# ==============================
@dataclass
class ConfirmedMenu:
    menu_id: str
    menu: str  # canonical
    ingredients: List[str]
    alg_tags: List[str]
    # optional: if exact hit was through variants, store the matched alias
    matched_variant: str = ""
    # ✅ NEW: short Korean description (optional)
    menu_description_ko: str = ""


class ChromaMenuRetriever:
    def __init__(
        self,
        chroma_dir: Optional[Path] = None,
        collection_name: Optional[str] = None,
        embed_model: Optional[str] = None,
    ):
        chroma_env = os.environ.get(ENV_CHROMA_DIR)
        self.chroma_dir = (
            Path(chroma_env).expanduser().resolve()
            if chroma_env
            else (chroma_dir.expanduser().resolve() if chroma_dir else None)
        )

        self.collection_name = os.environ.get(ENV_COLLECTION) or (collection_name or DEFAULT_COLLECTION)
        self.embed_model = os.environ.get(ENV_EMBED_MODEL) or (embed_model or DEFAULT_EMBED_MODEL)

        self._client = None
        self._collection = None

    def _init(self) -> None:
        if self._collection is not None:
            return

        if not self.chroma_dir.exists():
            s3_prefix = os.environ.get(ENV_CHROMA_S3_PREFIX, "").strip()
            if s3_prefix:
                _download_s3_prefix(s3_prefix, self.chroma_dir)
        if not self.chroma_dir.exists():
            raise RuntimeError(f"[RAG] chroma_dir does not exist: {self.chroma_dir}")

        emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=self.embed_model)
        self._client = chromadb.PersistentClient(path=str(self.chroma_dir))
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=emb_fn,
        )

        # fail-fast if empty
        try:
            if self._collection.count() == 0:
                raise RuntimeError(
                    f"[RAG] collection is empty. chroma_dir={self.chroma_dir} collection={self.collection_name}"
                )
        except Exception:
            got = self._collection.get(limit=1, include=["metadatas"])
            if not (got.get("ids") or []):
                raise RuntimeError(
                    f"[RAG] collection is empty. chroma_dir={self.chroma_dir} collection={self.collection_name}"
                )

    @property
    def collection(self):
        self._init()
        return self._collection

    def get_exact(self, menu_norm: str) -> Optional[ConfirmedMenu]:
        q = _norm_ws(menu_norm)
        if not q:
            return None

        # 1) where filter (best)
        try:
            got = self.collection.get(where={"menu": q}, include=["metadatas"])
            ids = got.get("ids") or []
            mds = got.get("metadatas") or []
            if ids and mds and isinstance(mds[0], dict):
                md0 = mds[0]
                menu_md = _norm_ws(str(md0.get("menu", "")))
                if menu_md == q:
                    return ConfirmedMenu(
                        menu_id=str(ids[0]),
                        menu=menu_md,
                        ingredients=_split_csv_like(md0.get("ingredients")),
                        alg_tags=_split_csv_like(md0.get("alg_tags")),
                        matched_variant="",
                        menu_description_ko=str(md0.get("menu_description_ko") or "").strip(),
                    )
        except Exception:
            pass

        # 2) fallback: semantic query then exact scan
        try:
            raw = self.collection.query(query_texts=[q], n_results=50, include=["metadatas", "ids"])
            ids = (raw.get("ids") or [[]])[0]
            mds = (raw.get("metadatas") or [[]])[0]
            for i, md in enumerate(mds or []):
                if not isinstance(md, dict):
                    continue
                menu_md = _norm_ws(str(md.get("menu", "")))

                # ✅ 2-1) canonical menu exact
                if menu_md == q:
                    menu_id = str(ids[i]) if i < len(ids) else f"idx_{i}"
                    return ConfirmedMenu(
                        menu_id=menu_id,
                        menu=menu_md,
                        ingredients=_split_csv_like(md.get("ingredients")),
                        alg_tags=_split_csv_like(md.get("alg_tags")),
                        matched_variant="",
                        menu_description_ko=str(md.get("menu_description_ko") or "").strip(),
                    )

                # ✅ 2-2) variants exact (alias -> canonical)
                variants = _split_csv_like(md.get("variants"))
                variants_norm = [_norm_ws(v) for v in variants]
                if q in variants_norm:
                    menu_id = str(ids[i]) if i < len(ids) else f"idx_{i}"
                    return ConfirmedMenu(
                        menu_id=menu_id,
                        menu=menu_md,
                        ingredients=_split_csv_like(md.get("ingredients")),
                        alg_tags=_split_csv_like(md.get("alg_tags")),
                        matched_variant=q,
                        menu_description_ko=str(md.get("menu_description_ko") or "").strip(),
                    )
        except Exception:
            pass

        return None


_DEFAULT: Optional[ChromaMenuRetriever] = None


def get_retriever() -> ChromaMenuRetriever:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = ChromaMenuRetriever()
    return _DEFAULT


def match_exact(menu_norm: str) -> Dict[str, Any]:
    """
    Returns:
      {
        "status": "exact" | "unknown",
        "used_query": <normalized menu_norm or None>,
        "confirmed": {menu_id, menu, ingredients, alg_tags} | None
      }
    """
    q = _norm_ws(menu_norm)
    if not q:
        return {"status": "unknown", "used_query": None, "confirmed": None}

    r = get_retriever()
    hit = r.get_exact(q)
    if hit is None:
        return {"status": "unknown", "used_query": q, "confirmed": None}

    return {
        "status": "exact",
        "used_query": q,
        "confirmed": {
            "menu_id": hit.menu_id,
            "menu": hit.menu,
            "ingredients": hit.ingredients,
            "alg_tags": hit.alg_tags,
            "matched_variant": hit.matched_variant or None,
            # ✅ NEW: short Korean description (optional)
            "menu_description_ko": hit.menu_description_ko,
        },
    }
