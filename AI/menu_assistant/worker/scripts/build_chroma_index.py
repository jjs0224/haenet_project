"""menu_assistant.worker.scripts.build_chroma_index

ChromaDB 인덱스 빌드 스크립트.

호환성 목표
- retrieval.py는 아래 메타데이터 키를 사용합니다.
  - menu (str)
  - variants (csv str 또는 list)
  - ingredients (csv str 또는 list)
  - alg_tags (csv str 또는 list)
  - source (str)
- ✅ (NEW) menu_description_ko (str) : 메뉴 한국어 간단 설명(옵션)
- 임베딩 모델/컬렉션/퍼시스트 디렉터리는 build와 retrieval이 동일해야 합니다.

기본 경로 정책
- 본 파일의 위치가 menu_assistant/worker/scripts/ 아래에 있는 것을 전제로,
  `BASE_DIR = <...>/menu_assistant` 를 자동 계산합니다.

권장 실행 예시(Windows)
python C:\\Users\\201\\Desktop\\PGHfolder\\haenet\\AI\\menu_assistant\\worker\\scripts\\build_chroma_index.py ^
  --dataset "C:\\Users\\201\\Desktop\\PGHfolder\\haenet\\AI\\menu_assistant\\data\\datasets\\raw\\menu_representative_korean_dedup_plus_cuisines.json" ^
  --chroma_dir "C:\\Users\\201\\Desktop\\PGHfolder\\haenet\\AI\\menu_assistant\\data\\chroma" ^
  --collection "menu_index" ^
  --embed_model "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions


# ==============================
# DEFAULT CONFIG (retrieval.py와 동일 권장)
# ==============================
DEFAULT_COLLECTION_NAME = "menu_index"
DEFAULT_BATCH_SIZE = 2000
DEFAULT_EMBED_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# ==============================
# DEFAULT PATHS (menu_assistant 기준)
# ==============================
BASE_DIR = Path(__file__).resolve().parents[2]  # menu_assistant/
DEFAULT_DATASET_PATH = (
    BASE_DIR
    / "data"
    / "datasets"
    / "raw"
    / "menu_seed.json"
)
DEFAULT_CHROMA_DIR = BASE_DIR / "data" / "chroma"


def _safe_str_list(x: Any) -> List[str]:
    if x is None:
        return []
    if isinstance(x, list):
        return [str(v).strip() for v in x if str(v).strip()]
    s = str(x).strip()
    return [s] if s else []


def _safe_str(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, str):
        return x.strip()
    return str(x).strip()


def _chunked(n: int, size: int):
    for i in range(0, n, size):
        yield i, min(i + size, n)


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build ChromaDB index for menu dataset")
    p.add_argument(
        "--dataset",
        default=str(DEFAULT_DATASET_PATH),
        help="Path to dataset JSON (list of records)",
    )
    p.add_argument(
        "--chroma_dir",
        default=str(DEFAULT_CHROMA_DIR),
        help="Chroma persist directory",
    )
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
    p.add_argument(
        "--batch_size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="Insert batch size",
    )
    p.add_argument(
        "--rebuild",
        action="store_true",
        help="Delete existing collection before build",
    )
    p.add_argument(
        "--source",
        default="menu_dataset",
        help="metadata['source'] value",
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

    # Persist 보장: PersistentClient 우선
    if hasattr(chromadb, "PersistentClient"):
        client = chromadb.PersistentClient(path=str(chroma_dir))
    else:
        client = chromadb.Client(
            Settings(persist_directory=str(chroma_dir), anonymized_telemetry=False)
        )

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

    # 문서는 '메뉴명 + variants' 중심으로 임베딩 (retrieval의 menu_norm/variants 비교와 정합)
    for idx, item in enumerate(data):
        menu = str(item.get("menu", "")).strip()
        if not menu:
            continue

        ingredients = _safe_str_list(item.get("ingredients"))
        # 호환: alg_tags 또는 ALG_TAG
        alg_tags = _safe_str_list(item.get("alg_tags") or item.get("ALG_TAG"))
        variants = _safe_str_list(item.get("variants"))

        # ✅ NEW: 메뉴 간단 설명(있으면 저장)
        menu_description_ko = _safe_str(item.get("menu_description_ko"))

        rid = str(item.get("id") or f"menu_{idx}")
        doc = " ".join([menu] + variants).strip()

        ids.append(rid)
        documents.append(doc)
        metadatas.append(
            {
                "menu": menu,
                # retrieval._split_csv는 csv string 또는 list 모두 처리 가능.
                # 여기서는 csv string으로 저장하여 Chroma metadata 크기를 줄인다.
                "variants": ", ".join(variants),
                "ingredients": ", ".join(ingredients),
                "alg_tags": ", ".join(alg_tags),
                "source": source,
                # ✅ NEW
                "menu_description_ko": menu_description_ko,
            }
        )

    total = len(ids)
    print(f"[INFO] Prepared insert records: {total}")
    if total == 0:
        raise ValueError("No insertable records. Check dataset field 'menu'.")

    for s, e in _chunked(total, batch_size):
        collection.add(
            ids=ids[s:e],
            documents=documents[s:e],
            metadatas=metadatas[s:e],
        )
        print(f"[INFO] Inserted {e}/{total}")

    # 삽입 검증
    try:
        cnt = collection.count()
    except Exception:
        got = collection.get(limit=5, include=["metadatas"])
        cnt = len(got.get("ids", []))

    print(f"[VERIFY] collection.count() = {cnt}")
    if cnt == 0:
        raise RuntimeError(
            "Build finished but collection is empty. Check persist directory / permissions."
        )

    sample = collection.get(limit=3, include=["metadatas"])
    metas = sample.get("metadatas") or []
    print("[SAMPLE] ids:", sample.get("ids"))
    print("[SAMPLE] menus:", [m.get("menu") for m in metas])
    # ✅ NEW: 샘플에 description도 찍어 확인
    print("[SAMPLE] menu_description_ko:", [m.get("menu_description_ko") for m in metas])

    print("[SUCCESS] Chroma index build complete.")


if __name__ == "__main__":
    main()
