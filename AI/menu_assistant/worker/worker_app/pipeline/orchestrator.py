from __future__ import annotations

from time import perf_counter
import os
import sys
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, List
import json
# ============================================================
# Path routing (Docker-friendly)
# ============================================================

def _project_root() -> Path:
    """
    Resolve repository/project root robustly.
    This file is: <root>/AI/menu_assistant/worker/worker_app/pipeline/orchestrator.py
    parents: [pipeline, worker_app, worker, menu_assistant, AI, <root>]
    """
    here = Path(__file__).resolve()
    return here.parents[5]


def _default_image_base() -> Path:
    """
    Default image base.
    Priority:
      1) ENV: MENU_ASSISTANT_IMAGE_BASE
      2) <project_root>/AI/Upload_Images
    """
    env = os.environ.get("MENU_ASSISTANT_IMAGE_BASE")
    if env:
        return Path(env).expanduser().resolve()
    return (_project_root() / "AI" / "Upload_Images").resolve()


def _default_runs_root() -> Path:
    """
    Default runs root.
    Priority:
      1) ENV: MENU_ASSISTANT_RUNS_ROOT
      2) <project_root>/AI/menu_assistant/data/runs
    """
    env = os.environ.get("MENU_ASSISTANT_RUNS_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    return (_project_root() / "AI" / "menu_assistant" / "data" / "runs").resolve()


def _resolve_image_arg(image_arg: str, image_base: Path) -> Path:
    """
    Resolve --image into absolute path.

    Supported:
      - absolute path
      - Upload_Images/xxx.jpg  -> <image_base>/xxx.jpg
      - xxx.jpg                -> <image_base>/xxx.jpg (if exists)
      - otherwise, relative to CWD
    """
    p = Path(image_arg)
    if p.is_absolute():
        return p

    parts = p.parts
    if parts and parts[0].lower() == "upload_images":
        tail = Path(*parts[1:]) if len(parts) > 1 else Path()
        return (image_base / tail).resolve()

    candidate = (image_base / p).resolve()
    if candidate.exists():
        return candidate

    return p.resolve()


# ============================================================
# Utilities
# ============================================================

def make_run_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def run_cmd(cmd: List[str], env: Optional[dict] = None, cwd: Optional[Path] = None) -> None:
    """Run a command and raise on failure (with captured stdout/stderr)."""
    print("\n[RUN]", " ".join(cmd))

    p = subprocess.run(
        cmd,
        shell=False,
        env=env,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if p.stdout:
        print(p.stdout)
    if p.stderr:
        print(p.stderr)

    if p.returncode != 0:
        raise RuntimeError(
            f"Command failed (exit={p.returncode}): {' '.join(cmd)}\n"
            f"--- stdout ---\n{(p.stdout or '').strip()}\n"
            f"--- stderr ---\n{(p.stderr or '').strip()}\n"
        )


def ensure_exists(path: Path, msg: str) -> None:
    if not path.exists():
        raise RuntimeError(f"{msg}: {path}")


def _resolve_chroma_dir(data_dir: Path, chroma_dir_arg: Optional[str]) -> Path:
    """
    Resolve chroma persist directory deterministically.

    Priority:
      1) --chroma-dir CLI argument
      2) <data_dir>/chroma (if exists)
      3) Windows known path fallback (only on Windows)
      4) <data_dir>/chroma (even if missing; downstream fails fast)
    """
    if chroma_dir_arg:
        return Path(chroma_dir_arg).expanduser().resolve()

    candidate = (data_dir / "chroma")
    if candidate.exists():
        return candidate.resolve()

    if os.name == "nt":
        win_fallback = Path(r"C:\Users\201\Desktop\PGHfolder\haenet\AI\menu_assistant\data\chroma")
        if win_fallback.exists():
            return win_fallback

    return candidate


# ============================================================
# Orchestrator options
# ============================================================

@dataclass
class Step1Options:
    backend: str = "auto"  # {none,doctr,dewarpnet,docunet,auto}
    device: str = "cpu"
    model_dir: Optional[str] = None
    gamma: float = 1.15
    clahe_clip: float = 2.0
    shadow_strength: float = 0.85


@dataclass
class Step2Options:
    lang: str = "korean"
    det_limit_side_len: int = 4000
    det_limit_type: str = "max"
    use_doc_unwarping: bool = False
    use_textline_orientation: bool = False
    det_model_dir: Optional[str] = None
    rec_model_dir: Optional[str] = None
    cls_model_dir: Optional[str] = None
    det_box_thresh: Optional[float] = None
    det_thresh: Optional[float] = None
    det_unclip_ratio: Optional[float] = None

    use_preprocess: bool = False
    preprocess_mode: Optional[str] = None

    dump_raw: bool = False
    out: Optional[str] = None
    vis: Optional[str] = None

    # PaddleOCR device control
    ocr_device: str = "auto"  # auto|cpu|gpu
    ocr_gpu_mem: Optional[int] = None
    cuda_visible_devices: Optional[str] = None


@dataclass
class Step3Options:
    min_len: int = 1
    min_score: float = 0.0


@dataclass
class Step4Options:
    chroma_dir: Optional[str] = None
    collection: str = "menu_index"


@dataclass
class Step5Options:
    user_profile_json: Optional[str] = None
    include_debug: bool = True
    max_retries: int = 2
    require_poly: bool = True
    sleep_base: float = 2.0  # orchestrator-level backoff

    # ✅ speed patch (Step05 chunk/parallel/cache)
    chunk_size: int = 8       # 0이면 기존처럼 단일 호출
    workers: int = 2          # 병렬 worker (권장 2~4)
    use_cache: bool = True   # llm/llm_cache.json 사용



@dataclass
class Step6Options:
    model: str = "gemini-2.5-flash"
    api_key_env: str = "GEMINI_API_KEY"

    temperature: float = 0.2
    top_p: float = 0.95
    top_k: int = 20

    max_retries: int = 2
    sleep_base: float = 0.7

    dotenv_path: Optional[str] = None
    max_dotenv_up: int = 8

    # ✅ performance / behavior options (patched Step06)
    batch_size: int = 5
    use_cache: bool = False
    force_translate_all: bool = False

    # ✅ menu_name_en control
    translate_menu_name: bool = False
    force_menu_name_en: bool = False


    # ✅ parallel (patched Step06)
    max_workers: int = 4
    parallel_singles: bool = False



class PipelineOrchestrator:
    def __init__(self, runs_root: Path, data_dir: Optional[Path] = None):
        self.runs_root = runs_root
        self.data_dir = (data_dir if data_dir is not None else runs_root.parent)

        # orchestrator.py: <root>/AI/menu_assistant/worker/worker_app/pipeline/orchestrator.py
        here = Path(__file__).resolve()
        self.ai_root = here.parents[4]  # .../AI

        # ensure import works under FastAPI subprocess
        ai_root_str = str(self.ai_root)
        if ai_root_str not in sys.path:
            sys.path.insert(0, ai_root_str)

    def run(
        self,
        image_path: Path,
        run_id: Optional[str] = None,
        *,
        step1: Optional[Step1Options] = None,
        step2: Optional[Step2Options] = None,
        step3: Optional[Step3Options] = None,
        step4: Optional[Step4Options] = None,
        step5: Optional[Step5Options] = None,
        step6: Optional[Step6Options] = None,
        run_step4: bool = True,
        run_step5: bool = True,
        run_step6: bool = True,
        do_check: bool = True,
        check_keywords: Optional[List[str]] = None,
        show_structured: bool = True,
    ) -> Path:
        if not image_path.exists():
            raise FileNotFoundError(f"Input image not found: {image_path}")

        step1 = step1 or Step1Options()
        step2 = step2 or Step2Options()
        step3 = step3 or Step3Options()
        step4 = step4 or Step4Options()
        step5 = step5 or Step5Options()
        step6 = step6 or Step6Options()

        run_id = run_id or make_run_id()
        run_dir = self.runs_root / run_id
        # -------------------------------
        # Timing (run-level)
        # -------------------------------
        timings: dict[str, float] = {}
        t_pipeline_start = perf_counter()

        def _fmt(sec: float) -> str:
            m, s = divmod(sec, 60.0)
            h, m = divmod(m, 60.0)
            if h >= 1:
                return f"{int(h)}h {int(m):02d}m {s:05.2f}s"
            return f"{int(m):02d}m {s:05.2f}s"

        def _mark(name: str, t0: float) -> None:
            timings[name] = perf_counter() - t0

        rectify_img = run_dir / "rectify" / "rectified.jpg"
        ocr_json_default = run_dir / "ocr" / "ocr.json"
        normalize_json = run_dir / "normalize" / "normalize.json"
        rag_match_json = run_dir / "rag_match" / "rag_match.json"
        final_json = run_dir / "final" / "final.json"
        translate_json = run_dir / "translate" / "translate.json"
        final_translated_json = run_dir / "final" / "final_translated.json"

        # ----------------------------------------------------
        # Step 01: Rectify
        # ----------------------------------------------------
        t0 = perf_counter()
        cmd1 = [
            sys.executable,
            "-m",
            "menu_assistant.worker.worker_app.pipeline.steps.step_01_rectify",
            "--input", str(image_path),
            "--run_id", run_id,
            "--data_dir", str(self.data_dir),
            "--run_dir", str(run_dir),
            "--backend", step1.backend,
            "--device", step1.device,
            "--gamma", str(step1.gamma),
            "--clahe_clip", str(step1.clahe_clip),
            "--shadow_strength", str(step1.shadow_strength),
        ]
        if step1.model_dir:
            cmd1 += ["--model_dir", step1.model_dir]

        run_cmd(cmd1, cwd=self.ai_root)
        ensure_exists(rectify_img, "Step01 expected output missing (rectified image)")
        _mark("step01_rectify", t0)
        # ----------------------------------------------------
        # Step 02: OCR
        # ----------------------------------------------------
        t0 = perf_counter()
        cmd2 = [
            sys.executable,
            "-m",
            "menu_assistant.worker.worker_app.pipeline.steps.step_02_ocr",
            "--run_id", run_id,
            "--data_dir", str(self.data_dir),
            "--run_dir", str(run_dir),
            "--lang", step2.lang,
            "--det_limit_side_len", str(step2.det_limit_side_len),
            "--det_limit_type", step2.det_limit_type,
            "--device", step2.ocr_device,
        ]
        if step2.ocr_gpu_mem is not None:
            cmd2 += ["--gpu_mem", str(step2.ocr_gpu_mem)]

        if step2.use_doc_unwarping:
            cmd2 += ["--use_doc_unwarping"]
        if step2.use_textline_orientation:
            cmd2 += ["--use_textline_orientation"]
        if step2.det_model_dir:
            cmd2 += ["--det_model_dir", step2.det_model_dir]
        if step2.rec_model_dir:
            cmd2 += ["--rec_model_dir", step2.rec_model_dir]
        if step2.cls_model_dir:
            cmd2 += ["--cls_model_dir", step2.cls_model_dir]

        if step2.use_preprocess:
            cmd2 += ["--use_preprocess"]
            if step2.preprocess_mode:
                cmd2 += ["--preprocess_mode", step2.preprocess_mode]

        if step2.dump_raw:
            cmd2 += ["--dump_raw"]
        if step2.out:
            cmd2 += ["--out", step2.out]
        if step2.vis:
            cmd2 += ["--vis", step2.vis]

        if step2.det_box_thresh is not None:
            cmd2 += ["--det_box_thresh", str(step2.det_box_thresh)]
        if step2.det_thresh is not None:
            cmd2 += ["--det_thresh", str(step2.det_thresh)]
        if step2.det_unclip_ratio is not None:
            cmd2 += ["--det_unclip_ratio", str(step2.det_unclip_ratio)]

        step2_env = os.environ.copy()
        step2_env["FLAGS_use_mkldnn"] = "0"
        step2_env["FLAGS_use_onednn"] = "0"
        step2_env["FLAGS_enable_pir_api"] = "0"
        step2_env["FLAGS_enable_pir_in_executor"] = "0"
        if step2.cuda_visible_devices:
            step2_env["CUDA_VISIBLE_DEVICES"] = str(step2.cuda_visible_devices)

        run_cmd(cmd2, env=step2_env, cwd=self.ai_root)

        ocr_json_check = Path(step2.out) if step2.out else ocr_json_default
        ensure_exists(ocr_json_check, "Step02 expected output missing (ocr json)")
        _mark("step02_ocr", t0)
        # ----------------------------------------------------
        # Step 03: Normalize
        # ----------------------------------------------------
        t0 = perf_counter()
        cmd3 = [
            sys.executable,
            "-m",
            "menu_assistant.worker.worker_app.pipeline.steps.step_03_normalize",
            "--runs-root", str(self.runs_root),
            "--run-id", run_id,
            "--min-len", str(step3.min_len),
            "--min-score", str(step3.min_score),
        ]
        run_cmd(cmd3, cwd=self.ai_root)
        ensure_exists(normalize_json, "Step03 expected output missing (normalize json)")
        _mark("step03_normalize", t0)
        # Optional: Step03 checker
        if do_check:
            t0 = perf_counter()
            check_cmd = [
                sys.executable,
                "-m",
                "menu_assistant.worker.worker_app.utils.check_step_03_result",
                "--json", str(normalize_json),
            ]
            if show_structured:
                check_cmd += ["--show-structured"]
            if check_keywords:
                check_cmd += ["--keywords"] + list(check_keywords)
            run_cmd(check_cmd, cwd=self.ai_root)
            _mark("step03_checker", t0)

        # ----------------------------------------------------
        # Step 04: RAG Match (EXACT-ONLY)
        # env routing only
        # ----------------------------------------------------

        if run_step4:
            t0 = perf_counter()
            chroma_dir = _resolve_chroma_dir(self.data_dir, step4.chroma_dir)
            step4_env = os.environ.copy()
            step4_env["MENU_ASSISTANT_CHROMA_DIR"] = str(chroma_dir)
            step4_env["MENU_ASSISTANT_COLLECTION"] = step4.collection

            print("\n[RAG] using chroma_dir   =", step4_env["MENU_ASSISTANT_CHROMA_DIR"])
            print("[RAG] using collection  =", step4_env["MENU_ASSISTANT_COLLECTION"])

            menu_index_json = os.environ.get(
                "MENU_ASSISTANT_MENU_INDEX_JSON",
                "/tmp/menu_seed_with_alg_tags_variants_v3.json",
            )

            cmd4 = [
                sys.executable,
                "-m",
                "menu_assistant.worker.worker_app.pipeline.steps.step_04_rag_match",
                "--run_id", run_id,
                "--data_dir", str(self.data_dir),
                "--run_dir", str(run_dir),
                "--top_k",
                str(step4.top_k),
                "--embed_ambiguous",
                str(step4.embed_ambiguous),
                "--jamo_threshold",
                str(step4.jamo_threshold),
                "--score_threshold",
                str(step4.score_threshold),
                "--save_top_n",
                str(step4.save_top_n),

                # (호환용: step_04는 받기만 함)
                "--rerank_top_k",
                str(step4.rerank_top_k),
                "--menu_index_json",
                menu_index_json
            ]

            if step4.use_rerank:
                cmd4 += ["--use_rerank"]
            else:
                cmd4 += ["--no_rerank"]

            if step4.include_debug:
                cmd4 += ["--include_debug"]

            run_cmd(cmd4, env=step4_env, cwd=self.ai_root)
            ensure_exists(rag_match_json, "Step04 expected output missing (rag_match json)")
            _mark("step04_rag_match", t0)
        # ----------------------------------------------------
        # Step 05: Risk Score (LLM) -> final.json is produced here
        # ----------------------------------------------------
        if run_step5:
            t0 = perf_counter()
            cmd5 = [
                sys.executable,
                "-m",
                "menu_assistant.worker.worker_app.pipeline.steps.step_05_risk_score",
                "--run_id", run_id,
                "--data_dir", str(self.data_dir),
                "--run_dir", str(run_dir),
                "--max_retries", str(step5.max_retries),
            ]
            if step5.user_profile_json:
                cmd5 += ["--user_profile_json", step5.user_profile_json]
            if step5.require_poly:
                cmd5 += ["--require_poly"]
            else:
                cmd5 += ["--no_require_poly"]
            if step5.include_debug:
                cmd5 += ["--include_debug"]
            # ✅ Step05 speed patch args
            if int(getattr(step5, "chunk_size", 0) or 0) > 0:
                cmd5 += ["--chunk_size", str(int(step5.chunk_size))]

            if int(getattr(step5, "workers", 1) or 1) > 1:
                cmd5 += ["--workers", str(int(step5.workers))]

            if bool(getattr(step5, "use_cache", False)):
                cmd5 += ["--use_cache"]


            # orchestrator-level backoff retry (subprocess)
            for attempt in range(int(step5.max_retries) + 1):
                try:
                    if attempt > 0:
                        wait = float(step5.sleep_base) * (2 ** (attempt - 1))
                        print(f"[STEP05] retrying in {wait:.1f}s... (attempt {attempt}/{step5.max_retries})")
                        time.sleep(wait)
                    run_cmd(cmd5, cwd=self.ai_root)
                    break
                except Exception:
                    if attempt >= int(step5.max_retries):
                        raise

            ensure_exists(final_json, "Step05 expected output missing (final.json)")
            _mark("step05_risk_score", t0)
        # ----------------------------------------------------
        # Step 06: Translate (final.json -> final_translated.json)
        # (Step6 내부에서 translate output schema validation 수행)
        # ----------------------------------------------------
        if run_step6:
            t0 = perf_counter()
            ensure_exists(final_json, "Step06 requires Step05 output (final.json)")

            cmd6 = [
                sys.executable,
                "-m",
                "menu_assistant.worker.worker_app.pipeline.steps.step_06_translate",
                "--run_id", run_id,
                "--data_dir", str(self.data_dir),
                "--run_dir", str(run_dir),
                "--model", step6.model,
                "--api_key_env", step6.api_key_env,
                "--temperature", str(step6.temperature),
                "--top_p", str(step6.top_p),
                "--top_k", str(step6.top_k),
                "--max_retries", str(step6.max_retries),
                "--sleep_base", str(step6.sleep_base),
                "--max_dotenv_up", str(step6.max_dotenv_up),
            ]
            if step6.dotenv_path:
                cmd6 += ["--dotenv_path", step6.dotenv_path]

            # ✅ patched Step06 args
            if int(step6.batch_size) > 1:
                cmd6 += ["--batch_size", str(int(step6.batch_size))]
            if step6.use_cache:
                cmd6 += ["--use_cache"]
            if step6.force_translate_all:
                cmd6 += ["--force_translate_all"]

            if step6.translate_menu_name:
                cmd6 += ["--translate_menu_name"]
                if step6.force_menu_name_en:
                    cmd6 += ["--force_menu_name_en"]

            # ✅ Step06 parallel flags
            if getattr(step6, "parallel_singles", False):
                cmd6 += ["--parallel_singles"]
            if int(getattr(step6, "max_workers", 0) or 0) > 0:
                cmd6 += ["--max_workers", str(int(step6.max_workers))]

            run_cmd(cmd6, cwd=self.ai_root)

            ensure_exists(translate_json, "Step06 expected output missing (translate.json)")
            ensure_exists(final_translated_json, "Step06 expected output missing (final_translated.json)")

            # ✅ FRONT 기준: final_translated.json을 "공식 최종본"으로 명시 (덮어쓰기 없음)
            final_output_meta = {
                "schema_version": "v1",
                "run_id": run_id,
                "final_output": {
                    "type": "final_translated",
                    "relative_path": str(Path("final") / "final_translated.json"),
                },
                "artifacts": {
                    "rectified_image": str(rectify_img),
                    "final_json": str(final_json),
                    "translate_json": str(translate_json),
                    "final_translated_json": str(final_translated_json),
                },
            }
            final_output_path = run_dir / "final" / "final_output.json"
            final_output_path.write_text(
                json.dumps(final_output_meta, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"[STEP06] wrote final_output.json : {final_output_path}")
            _mark("step06_translate", t0)

        # -------------------------------
        # Timing summary
        # -------------------------------
        t_total = perf_counter() - t_pipeline_start

        print("\n=== STEP TIMING SUMMARY ===")
        rows = [
            ("step01_rectify", "01 Rectify"),
            ("step02_ocr", "02 OCR"),
            ("step03_normalize", "03 Normalize"),
            ("step03_checker", "03 Checker"),
            ("step04_rag_match", "04 RAG Match"),
            ("step05_risk_score", "05 Risk Score"),
            ("step06_translate", "06 Translate"),
        ]
        for key, label in rows:
            if key in timings:
                print(f"{label:<14} : {_fmt(timings[key])}")

        sum_steps = sum(timings.values()) if timings else 0.0
        print(f"{'Sum(steps)':<14} : {_fmt(sum_steps)}")
        print(f"{'Total(run)':<14} : {_fmt(t_total)}")

        print("\n=== PIPELINE DONE (01~06) ===")
        print(f"run_dir               : {run_dir}")
        print(f"rectified.jpg         : {rectify_img}")
        print(f"ocr.json              : {ocr_json_check}")
        print(f"normalize.json        : {normalize_json}")
        if run_step4:
            print(f"rag_match.json        : {rag_match_json}")
        if run_step5:
            print(f"final.json            : {final_json}")
        if run_step6:
            print(f"translate.json        : {translate_json}")
            print(f"final_translated.json : {final_translated_json}")
            print(f"final_output.json     : {run_dir / 'final' / 'final_output.json'}  (FRONT entrypoint)")
        return run_dir


# ============================================================
# CLI
# ============================================================
if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Pipeline Orchestrator: step_01 -> step_06")

    p.add_argument("--image", required=True, help="Input image path")
    p.add_argument("--runs-root", default=str(_default_runs_root()), help="Runs root directory")
    p.add_argument("--run-id", default=None, help="Optional run id. If omitted, auto-generated.")

    # ---------------- Step1 ----------------
    p.add_argument("--backend", default="auto", choices=["none", "doctr", "dewarpnet", "docunet", "auto"])
    p.add_argument("--device", default="cpu")
    p.add_argument("--model-dir", default="menu_assistant/worker/worker_app/vision/metrics/DewarpNet_master")
    p.add_argument("--gamma", type=float, default=1.0)
    p.add_argument("--clahe-clip", type=float, default=2.0)
    p.add_argument("--shadow-strength", type=float, default=0.0)

    # ---------------- Step2 ----------------
    p.add_argument("--lang", default="korean")
    p.add_argument("--det-limit-side-len", type=int, default=4000)
    p.add_argument("--det-limit-type", default="max")
    p.add_argument("--use-doc-unwarping", action="store_true")
    p.add_argument("--use-textline-orientation", action="store_true")
    p.add_argument("--det-model-dir", default=None)
    p.add_argument("--rec-model-dir", default=None)
    p.add_argument("--cls-model-dir", default=None)

    p.add_argument("--det-box-thresh", type=float, default=0.5)
    p.add_argument("--det-thresh", type=float, default=0.30)
    p.add_argument("--det-unclip-ratio", type=float, default=2.0)

    p.add_argument("--use-preprocess", action="store_true")
    p.add_argument("--preprocess-mode", default=None)

    p.add_argument("--dump-raw", action="store_true")
    p.add_argument("--ocr-out", default=None)
    p.add_argument("--ocr-vis", default=None)

    p.add_argument("--ocr-device", default="auto", choices=["auto", "cpu", "gpu"])
    p.add_argument("--ocr-gpu-mem", type=int, default=None)
    p.add_argument("--cuda-visible-devices", default=None)

    # ---------------- Step3 ----------------
    p.add_argument("--min-len", type=int, default=2)
    p.add_argument("--min-score", type=float, default=0.0)

    # ---------------- Step4 ----------------
    p.add_argument("--no-step4", action="store_true", help="Skip step4")
    p.add_argument("--chroma-dir", default=None)
    p.add_argument("--collection", default="menu_index")

    # ---------------- Step5 ----------------
    p.add_argument("--no-step5", action="store_true", help="Skip step5")
    p.add_argument("--user-profile-json", default=None)
    p.add_argument("--step5-debug", action="store_true")
    p.add_argument("--step5-max-retries", type=int, default=2)
    p.add_argument("--step5-no-require-poly", action="store_true")
    # ✅ Step05 speed patch
    p.add_argument("--step5-chunk-size", type=int, default=0)
    p.add_argument("--step5-workers", type=int, default=1)
    p.add_argument("--step5-use-cache", action="store_true")


    # ---------------- Step6 ----------------
    p.add_argument("--no-step6", action="store_true", help="Skip step6")
    p.add_argument("--step6-model", default="gemini-2.5-flash")
    p.add_argument("--step6-api-key-env", default="GEMINI_API_KEY")
    p.add_argument("--step6-temperature", type=float, default=0.2)
    p.add_argument("--step6-top-p", type=float, default=0.95)
    p.add_argument("--step6-top-k", type=int, default=40)
    p.add_argument("--step6-max-retries", type=int, default=2)
    p.add_argument("--step6-sleep-base", type=float, default=0.7)
    p.add_argument("--step6-dotenv-path", default=None)
    p.add_argument("--step6-max-dotenv-up", type=int, default=8)

    # ✅ patched Step06 flags
    p.add_argument("--step6-batch-size", type=int, default=2)
    p.add_argument("--step6-use-cache", action="store_true")
    p.add_argument("--step6-force-translate-all", action="store_true")

    p.add_argument("--step6-translate-menu-name", action="store_true")
    p.add_argument("--step6-force-menu-name-en", action="store_true")

    # ✅ Step06 parallel (patched)
    p.add_argument("--step6-parallel-singles", action="store_true")
    p.add_argument("--step6-max-workers", type=int, default=4)

    # ---------------- Step3 checker ----------------
    p.add_argument("--no-check", action="store_true")
    p.add_argument("--check-keywords", nargs="*", default=None)
    p.add_argument("--no-structured", action="store_true")

    args = p.parse_args()

    # Resolve image path
    image_base = _default_image_base()
    resolved_image = _resolve_image_arg(args.image, image_base)

    runs_root = Path(args.runs_root).expanduser().resolve()
    orch = PipelineOrchestrator(runs_root)

    step1 = Step1Options(
        backend=args.backend,
        device=args.device,
        model_dir=args.model_dir,
        gamma=args.gamma,
        clahe_clip=args.clahe_clip,
        shadow_strength=args.shadow_strength,
    )

    step2 = Step2Options(
        lang=args.lang,
        det_limit_side_len=args.det_limit_side_len,
        det_limit_type=args.det_limit_type,
        use_doc_unwarping=args.use_doc_unwarping,
        use_textline_orientation=args.use_textline_orientation,
        det_model_dir=args.det_model_dir,
        rec_model_dir=args.rec_model_dir,
        cls_model_dir=args.cls_model_dir,
        use_preprocess=args.use_preprocess,
        preprocess_mode=args.preprocess_mode,
        dump_raw=args.dump_raw,
        out=args.ocr_out,
        vis=args.ocr_vis,
        det_box_thresh=args.det_box_thresh,
        det_thresh=args.det_thresh,
        det_unclip_ratio=args.det_unclip_ratio,
        ocr_device=args.ocr_device,
        ocr_gpu_mem=args.ocr_gpu_mem,
        cuda_visible_devices=args.cuda_visible_devices,
    )

    step3 = Step3Options(
        min_len=args.min_len,
        min_score=args.min_score,
    )

    step4 = Step4Options(
        chroma_dir=args.chroma_dir,
        collection=args.collection,
    )

    step5 = Step5Options(
        user_profile_json=args.user_profile_json,
        include_debug=args.step5_debug,
        max_retries=args.step5_max_retries,
        require_poly=(not args.step5_no_require_poly),

        # ✅ Step05 speed patch
        chunk_size=args.step5_chunk_size,
        workers=args.step5_workers,
        use_cache=args.step5_use_cache,
    )

    step6 = Step6Options(
        model=args.step6_model,
        api_key_env=args.step6_api_key_env,
        temperature=args.step6_temperature,
        top_p=args.step6_top_p,
        top_k=args.step6_top_k,
        max_retries=args.step6_max_retries,
        sleep_base=args.step6_sleep_base,
        dotenv_path=args.step6_dotenv_path,
        max_dotenv_up=args.step6_max_dotenv_up,# ✅ patched Step06
        batch_size=args.step6_batch_size,
        use_cache=args.step6_use_cache,
        force_translate_all=args.step6_force_translate_all,
        translate_menu_name=args.step6_translate_menu_name,
        force_menu_name_en=args.step6_force_menu_name_en,
        # ✅ Step06 parallel (patched)
        parallel_singles=args.step6_parallel_singles,
        max_workers=args.step6_max_workers,
)

    orch.run(
        image_path=resolved_image,
        run_id=args.run_id,
        step1=step1,
        step2=step2,
        step3=step3,
        step4=step4,
        step5=step5,
        step6=step6,
        run_step4=(not args.no_step4),
        run_step5=(not args.no_step5),
        run_step6=(not args.no_step6),
        do_check=(not args.no_check),
        check_keywords=args.check_keywords,
        show_structured=(not args.no_structured),
    )
