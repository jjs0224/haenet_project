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
        self._variant_to_confirmed: Dict[str, ConfirmedMenu] = {}

    def _init(self) -> None:
        if self._collection is not None:
            return

        if self.chroma_dir is None:
            raise RuntimeError(f"[RAG] chroma_dir is not set. Set env {ENV_CHROMA_DIR} or pass chroma_dir.")

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

        self._build_variant_alias_map()

    def _build_variant_alias_map(self) -> None:
        self._variant_to_confirmed = {}
        coll = self._collection
        if coll is None:
            return

        try:
            total = int(coll.count())
        except Exception:
            total = 0

        if total <= 0:
            return

        page_size = 2000
        for offset in range(0, total, page_size):
            try:
                got = coll.get(limit=page_size, offset=offset, include=["metadatas"])
            except Exception:
                # Fallback for environments where offset is not available/reliable.
                if offset > 0:
                    break
                got = coll.get(limit=total, include=["metadatas"])

            ids = got.get("ids") or []
            mds = got.get("metadatas") or []
            if not ids or not mds:
                continue

            for i, md in enumerate(mds):
                if not isinstance(md, dict):
                    continue
                menu_md = _norm_ws(str(md.get("menu", "")))
                if not menu_md:
                    continue
                menu_id = str(ids[i]) if i < len(ids) else f"idx_{offset+i}"
                base = ConfirmedMenu(
                    menu_id=menu_id,
                    menu=menu_md,
                    ingredients=_split_csv_like(md.get("ingredients")),
                    alg_tags=_split_csv_like(md.get("alg_tags")),
                    matched_variant="",
                    menu_description_ko=str(md.get("menu_description_ko") or "").strip(),
                )

                for v in _split_csv_like(md.get("variants")):
                    vn = _norm_ws(v)
                    if not vn:
                        continue
                    key = vn.casefold()
                    # Keep first mapping when conflicts exist.
                    if key not in self._variant_to_confirmed:
                        self._variant_to_confirmed[key] = ConfirmedMenu(
                            menu_id=base.menu_id,
                            menu=base.menu,
                            ingredients=base.ingredients,
                            alg_tags=base.alg_tags,
                            matched_variant=vn,
                            menu_description_ko=base.menu_description_ko,
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

        # 1.5) deterministic variants exact (alias -> canonical)
        alias_hit = self._variant_to_confirmed.get(q.casefold())
        if alias_hit is not None:
            return alias_hit

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
