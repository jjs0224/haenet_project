# 0) 통합 실행코드
python -m menu_assistant.worker.worker_app.pipeline.orchestrator --image C:\Users\201\Desktop\PGHfolder\haenet\upload\image7.jpg --user-profile-json C:\Users\201\Desktop\PGHfolder\haenet\upload\user_profile_mock.json


# 1) 보정만 수행 (photometric-only)
python -m menu_assistant.worker.worker_app.pipeline.steps.step_01_rectify --input Upload_Images/image1.jpg --backend none
backend = [doctr,dewarpnet,docunet]
python -m menu_assistant.worker.worker_app.pipeline.steps.step_01_rectify --input Upload_Images/image1.jpg --backend doctr
python -m menu_assistant.worker.worker_app.pipeline.steps.step_01_rectify --input Upload_Images/image1.jpg --backend docunet
python -m AI.menu_assistant.worker.worker_app.pipeline.steps.step_01_rectify --input Upload_Images/image8.jpg --backend auto
# 2) paddleocr 작동
python -m menu_assistant.worker.worker_app.pipeline.steps.step_02_ocr --run_id 20260112_181356 --dump_raw
  --image menu_assistant/data/runs/20260112_181356/rectify/rectified.jpg ^
  --out   menu_assistant/data/runs/20260112_181356/ocr/ocr.json ^
  --vis   menu_assistant/data/runs/20260112_181356/ocr/ocr_vis.jpg

python -m menu_assistant.worker.worker_app.pipeline.steps.step_02_ocr ^
  --image Upload_Images/image7.jpg ^
  --out   menu_assistant/data/runs/20260112_181356/ocr/ocr.json ^
  --vis   menu_assistant/data/runs/20260112_181356/ocr/ocr_vis.jpg

# 3) normalize 실행
python -m menu_assistant.worker.worker_app.pipeline.steps.step_03_normalize --runs-root "C:\Users\201\Desktop\PGHfolder\haenet\uploads\tmp\menu\7242a839300e4f3a8c8dd99a8509b48d\ai_runs" --run-id 7242a839300e4f3a8c8dd99a8509b48d

# 4) rag match 메뉴명만 선매칭
python -m menu_assistant.worker.worker_app.pipeline.steps.step_04_rag_match ^
  --run_id 7242a839300e4f3a8c8dd99a8509b48d ^
  --top_k 20 ^
  --rerank_top_k 5 ^
  --use_rerank
# ChromaDB build
python -m menu_assistant.worker.scripts.build_chroma_index

#reduce_dataset
"""
python menu_assistant/data/datasets/raw/reduce_Dataset.py ^
  --input "C:\Users\201\Desktop\PGHfolder\Final_project\AI\menu_assistant\data\datasets\raw\menu_final_with_allergen.json" ^
  --output "C:\Users\201\Desktop\PGHfolder\Final_project\AI\menu_assistant\data\datasets\raw\menu_representatives_250.json" ^
  --mapping_out "C:\Users\201\Desktop\PGHfolder\Final_project\AI\menu_assistant\data\datasets\raw\menu_representatives_250_mapping.json" ^
  --target_n 250
"""

python -m menu_assistant.worker.worker_app.pipeline.steps.step_05_risk_score ^
  --run_id 20260204_174345 ^
  --data_dir C:\Users\201\Desktop\PGHfolder\haenet\AI\menu_assistant\data ^
  --run_dir C:\Users\201\Desktop\PGHfolder\haenet\AI\menu_assistant\data\runs\20260204_174345 ^
  --user_profile_json C:\Users\201\Desktop\PGHfolder\haenet\upload\user_profile_mock.json ^
  --require_poly


