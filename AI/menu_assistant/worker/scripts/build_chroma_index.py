"""Build ChromaDB index for menu dataset."""

from __future__ import annotations

import argparse
import json
import os
import re
import tarfile
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions


DEFAULT_COLLECTION_NAME = "menu_index"
DEFAULT_BATCH_SIZE = 2000
DEFAULT_EMBED_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

BASE_DIR = Path(__file__).resolve().parents[2]  # menu_assistant/
DEFAULT_DATASET_PATH = BASE_DIR / "data" / "datasets" / "raw" / "menu_seed.json"
DEFAULT_CHROMA_DIR = BASE_DIR / "data" / "chroma"

_WS_RE = re.compile(r"\s+")


def _norm_ws(s: str) -> str:
    return _WS_RE.sub(" ", (s or "").strip())


def _safe_str_list(x: Any) -> List[str]:
    if x is None:
        return []
    if isinstance(x, list):
        return [_norm_ws(str(v)) for v in x if _norm_ws(str(v))]
    s = _norm_ws(str(x))
    return [s] if s else []


def _safe_str(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, str):
        return x.strip()
    return str(x).strip()


def _normalize_variants(x: Any, canonical_menu: str) -> List[str]:
    raw = _safe_str_list(x)
    seen = set()
    out: List[str] = []
    menu_norm = _norm_ws(canonical_menu)

    for v in raw:
        vn = _norm_ws(v)
        if not vn:
            continue
        # canonical menu string should not be duplicated as variant
        if menu_norm and vn == menu_norm:
            continue
        key = vn.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(vn)
    return out


def _chunked(n: int, size: int):
    for i in range(0, n, size):
        yield i, min(i + size, n)


def _upload_chroma_to_s3(chroma_dir: Path, s3_prefix: str) -> None:
    """Package chroma_dir as a tarball and upload to S3."""
    try:
        import boto3  # type: ignore
    except ImportError:
        print("[S3] boto3 not available; skipping S3 upload.")
        return

    s3_uri = s3_prefix.rstrip("/")
    if s3_uri.startswith("s3://"):
        rest = s3_uri[5:]
    else:
        rest = s3_uri
    parts = rest.split("/", 1)
    bucket = parts[0]
    key_prefix = parts[1] if len(parts) > 1 else ""
    tarball_key = f"{key_prefix}/chroma.tar.gz" if key_prefix else "chroma.tar.gz"

    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        print(f"[S3] Creating tarball: {tmp_path}")
        with tarfile.open(tmp_path, "w:gz") as tar:
            tar.add(str(chroma_dir), arcname="chroma")

        region = (
            os.environ.get("S3_REGION")
            or os.environ.get("AWS_REGION")
            or os.environ.get("AWS_DEFAULT_REGION")
        )
        client = boto3.client("s3", region_name=region) if region else boto3.client("s3")

        print(f"[S3] Uploading s3://{bucket}/{tarball_key} ...")
        client.upload_file(tmp_path, bucket, tarball_key)
        print(f"[S3] Upload complete: s3://{bucket}/{tarball_key}")
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build ChromaDB index for menu dataset")
    p.add_argument("--dataset", default=str(DEFAULT_DATASET_PATH), help="Path to dataset JSON (list of records)")
    p.add_argument("--chroma_dir", default=str(DEFAULT_CHROMA_DIR), help="Chroma persist directory")
    p.add_argument(
        "--collection",
        default=DEFAULT_COLLECTION_NAME,
        help="Chroma collection name (must match retrieval.py)",
    )
    p.add_argument(
        "--embed_model",
        default=DEFAULT_EMBED_MODEL,
        help="SentenceTransformer model name (must match retrieval.py)",
    )
    p.add_argument("--batch_size", type=int, default=DEFAULT_BATCH_SIZE, help="Insert batch size")
    p.add_argument("--rebuild", action="store_true", help="Delete existing collection before build")
    p.add_argument("--source", default="menu_dataset", help="metadata['source'] value")
    p.add_argument(
        "--s3_prefix",
        default="",
        help="S3 prefix for chroma upload after build (e.g. s3://my-bucket/ai/chroma). "
        "Uploads chroma.tar.gz to <s3_prefix>/chroma.tar.gz.",
    )
    return p


def main() -> None:
    args = _build_argparser().parse_args()

    dataset_path = Path(args.dataset)
    chroma_dir = Path(args.chroma_dir)
    collection_name = str(args.collection)
    embed_model = str(args.embed_model)
    batch_size = int(args.batch_size)
    source = str(args.source)

    print(f"[INFO] BASE_DIR      : {BASE_DIR}")
    print(f"[INFO] DATASET_PATH  : {dataset_path}")
    print(f"[INFO] CHROMA_DIR    : {chroma_dir}")
    print(f"[INFO] COLLECTION    : {collection_name}")
    print(f"[INFO] EMBED_MODEL   : {embed_model}")
    print(f"[INFO] BATCH_SIZE    : {batch_size}")

    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset not found: {dataset_path}")

    with open(dataset_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("Dataset JSON must be a list of records")

    print(f"[INFO] Loaded records: {len(data)}")

    chroma_dir.mkdir(parents=True, exist_ok=True)

    emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=embed_model)

    if hasattr(chromadb, "PersistentClient"):
        client = chromadb.PersistentClient(path=str(chroma_dir))
    else:
        client = chromadb.Client(Settings(persist_directory=str(chroma_dir), anonymized_telemetry=False))

    if args.rebuild:
        try:
            client.delete_collection(collection_name)
            print("[INFO] Existing collection deleted.")
        except Exception:
            print("[INFO] No existing collection to delete (or delete failed).")

    collection = client.get_or_create_collection(name=collection_name, embedding_function=emb_fn)

    ids: List[str] = []
    documents: List[str] = []
    metadatas: List[Dict[str, Any]] = []

    for idx, item in enumerate(data):
        menu = _norm_ws(str(item.get("menu", "")))
        if not menu:
            continue

        ingredients = _safe_str_list(item.get("ingredients"))
        alg_tags = _safe_str_list(item.get("alg_tags") or item.get("ALG_TAG"))
        variants = _normalize_variants(item.get("variants"), menu)
        menu_description_ko = _safe_str(item.get("menu_description_ko"))

        rid = str(item.get("id") or f"menu_{idx}")
        doc = " ".join([menu] + variants).strip()

        ids.append(rid)
        documents.append(doc)
        metadatas.append(
            {
                "menu": menu,
                "variants": ", ".join(variants),
                "ingredients": ", ".join(ingredients),
                "alg_tags": ", ".join(alg_tags),
                "source": source,
                "menu_description_ko": menu_description_ko,
            }
        )

    total = len(ids)
    print(f"[INFO] Prepared insert records: {total}")
    if total == 0:
        raise ValueError("No insertable records. Check dataset field 'menu'.")

    for s, e in _chunked(total, batch_size):
        collection.add(ids=ids[s:e], documents=documents[s:e], metadatas=metadatas[s:e])
        print(f"[INFO] Inserted {e}/{total}")

    try:
        cnt = collection.count()
    except Exception:
        got = collection.get(limit=5, include=["metadatas"])
        cnt = len(got.get("ids", []))

    print(f"[VERIFY] collection.count() = {cnt}")
    if cnt == 0:
        raise RuntimeError("Build finished but collection is empty. Check persist directory / permissions.")

    sample = collection.get(limit=3, include=["metadatas"])
    metas = sample.get("metadatas") or []
    print("[SAMPLE] ids:", sample.get("ids"))
    print("[SAMPLE] menus:", [m.get("menu") for m in metas])
    print("[SAMPLE] menu_description_ko:", [m.get("menu_description_ko") for m in metas])

    print("[SUCCESS] Chroma index build complete.")

    if args.s3_prefix:
        _upload_chroma_to_s3(chroma_dir, args.s3_prefix)


if __name__ == "__main__":
    main()
