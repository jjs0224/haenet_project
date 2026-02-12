import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { MenuAPI } from "../../api/menuApi";
import PolygonOverlay from "./PolygonOverlay";
import MenuDetailModal from "./MenuDetailModal";
import "./ResultPage.css";

/**
 * 백엔드 응답 형태 방어적 표준화
 */
function normalizeBackendPayload(raw) {
  const root = raw?.data ?? raw;
  const payload = root?.result ?? root;
  const finalObj = payload?.final ?? payload?.final_obj ?? payload?.final_json ?? payload;

  const rectified = payload?.rectified_image ?? payload?.rectified ?? null;
  const base64 = rectified?.base64 ?? null;
  const mime = rectified?.mime ?? "image/jpeg";
  const imageDataUrl = base64 ? `data:${mime};base64,${base64}` : null;

  return { raw: root, payload, final: finalObj, imageDataUrl };
}

export default function ResultPage() {
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  // 페이지 진입 시 OCR 실행
  useEffect(() => {
    const file = window.__menuFile;
    window.__menuFile = null; // 사용 후 즉시 클리어

    if (!file) {
      navigate("/", { replace: true });
      return;
    }

    let cancelled = false;

    const run = async () => {
      try {
        const response = await MenuAPI.uploadMenu(file);
        if (cancelled) return;

        const jobId = response?.data?.job_id;
        const status = response?.data?.status;

        if (!jobId) {
          throw new Error("서버에서 job_id를 받지 못했어");
        }

        if (status === "DONE" && response?.data?.result) {
          setResult(response?.data ?? response);
          return;
        }

        const jobRes = await MenuAPI.waitMenuJob(jobId);
        if (cancelled) return;

        if (jobRes?.data?.status === "DONE") {
          setResult({ job_id: jobId, result: jobRes?.data?.result });
        } else {
          const err = jobRes?.data?.error;
          const errMsg = err?.message || err?.detail || JSON.stringify(err || {});
          setError(`분석 실패: ${errMsg}`);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err?.response?.data?.detail || err?.message || "분석 실패");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    run();

    return () => { cancelled = true; };
  }, [navigate]);

  // -------- 로딩 중 전체화면 오버레이 --------
  if (loading) {
    return (
      <div className="rp-loading-overlay">
        <div className="rp-loading-box">
          <div className="rp-spinner" />
          <p className="rp-loading-text">Analyzing the menu...</p>
        </div>
      </div>
    );
  }

  // -------- 오류 상태 --------
  if (error) {
    return (
      <div className="rp-error-wrap">
        <p className="rp-error-text">{error}</p>
        <button className="rp-back-btn" onClick={() => navigate("/")}>홈으로 돌아가기</button>
      </div>
    );
  }

  // -------- 결과 렌더 --------
  return <ResultContent result={result} />;
}

/* =========================================================
   결과 내용 컴포넌트 (기존 로직 유지)
   ========================================================= */
function ResultContent({ result }) {
  const navigate = useNavigate();
  const [selectedItem, setSelectedItem] = useState(null);
  const [imgSize, setImgSize] = useState({ w: 0, h: 0 });
  const [imgBroken, setImgBroken] = useState(false);

  const normalized = useMemo(() => normalizeBackendPayload(result), [result]);
  const items = result?.items || normalized?.final?.items || [];

  const imageUrl = result?.result_image_url || normalized?.imageDataUrl;
  const resolvedImageSrc = !imgBroken ? imageUrl : (normalized?.imageDataUrl || imageUrl);

  // const jsonText = (() => {
  //   try { return JSON.stringify(result ?? {}, null, 2); }
  //   catch (e) { return String(result); }
  // })();

  const getItemLabel = (item) =>
    item?.menu?.menu_name_en || item?.menu?.menu_name_ko || item?.menu_name_en || item?.menu_name_ko || "(no name)";

  // risk_difficulty 기반 테두리 색상
  const getBorderColor = (item) => {
    const riskDifficulty = item?.risk_difficulty ?? item?.risk?.risk_difficulty ?? null;
    const n = Number(riskDifficulty);
    if (n === 3) return "#9ca3af"; // gray
    if (n === 2) return "#ef4444"; // red
    if (n === 1) return "#f97316"; // orange
    if (n === 0) return "#16a34a"; // green
    return "#9ca3af"; // default gray
  };

  return (
    <div className="rp-container">
      {/* 다시 분석하기 버튼 */}
      <button className="rp-back-btn" onClick={() => navigate("/")}>Reanalyzing</button>

      {/* 결과 이미지 + PolygonOverlay */}
      <div className="rp-image-wrap">
        {resolvedImageSrc ? (
          <img
            src={resolvedImageSrc}
            alt="result"
            className="rp-image"
            onLoad={(e) => {
              setImgSize({ w: e.currentTarget.naturalWidth || 0, h: e.currentTarget.naturalHeight || 0 });
            }}
            onError={() => setImgBroken(true)}
          />
        ) : (
          <p className="rp-empty">No result image.</p>
        )}

        <PolygonOverlay
          items={items}
          imgSize={imgSize}
          onSelectItem={(item) => setSelectedItem(item)}
        />
      </div>

      {/* MenuDetailModal */}
      {selectedItem && (
        <MenuDetailModal item={selectedItem} onClose={() => setSelectedItem(null)} />
      )}

      {/* 감지된 메뉴 목록 */}
      {Array.isArray(items) && items.length > 0 && (
        <div className="rp-menu-section">
          <h3 className="rp-menu-title">Detected menus / choose the menu</h3>
          <div className="rp-menu-grid">
            {items.map((it, idx) => (
              <div
                key={it?.id || it?.item_id || idx}
                className="rp-menu-card"
                style={{ borderColor: getBorderColor(it) }}
                onClick={() => setSelectedItem(it)}
              >
                <div className="rp-menu-name">{getItemLabel(it)}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Result JSON */}
      {/* <div className="rp-json-wrap">
        <h3 className="rp-json-title">Result JSON</h3>
        <pre className="rp-json-pre">{jsonText}</pre>
      </div> */}
    </div>
  );
}
