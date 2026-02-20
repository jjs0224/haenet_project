import React, { useMemo, useState } from "react";
import PolygonOverlay from "./PolygonOverlay";
import MenuDetailModal from "./MenuDetailModal";
import './menuscan.css';

/* =========================
   Backend payload normalize
========================= */
function normalizeBackendPayload(raw) {
  const root = raw?.data ?? raw;
  const payload = root?.result ?? root;

  const finalObj =
    payload?.final ??
    payload?.final_obj ??
    payload?.final_json ??
    payload;

  // rectified image base64 fallback
  const rectified = payload?.rectified_image ?? payload?.rectified ?? null;
  const rectB64 = rectified?.base64 ?? null;
  const rectMime = rectified?.mime ?? "image/jpeg";
  const rectifiedDataUrl = rectB64 ? `data:${rectMime};base64,${rectB64}` : null;

  // result overlay image base64 fallback
  const resultImg = payload?.result_image ?? null;
  const resB64 = resultImg?.base64 ?? null;
  const resMime = resultImg?.mime ?? "image/jpeg";
  const resultDataUrl = resB64 ? `data:${resMime};base64,${resB64}` : null;

  // result overlay 우선, 없으면 rectified
  const imageDataUrl = resultDataUrl || rectifiedDataUrl;

  return {
    raw: root,
    payload,
    final: finalObj,
    imageDataUrl,
    rectifiedDataUrl
  };
}

export default function MenuAIResultView({
  result,
  onRestart
}) {
  const [selectedItem, setSelectedItem] = useState(null);
  const [imgSize, setImgSize] = useState({ w: 0, h: 0 });
  const [imgBroken, setImgBroken] = useState(false);

  const normalized = useMemo(
    () => normalizeBackendPayload(result),
    [result]
  );

  const items =
    result?.items ||
    normalized?.final?.items ||
    [];

  const imageUrl =
    result?.result_image_url ||
    result?.artifacts?.result_image?.presigned_url ||
    normalized?.payload?.result_image_url ||
    normalized?.payload?.artifacts?.result_image?.presigned_url ||
    result?.rectified_image_url ||
    result?.artifacts?.rectified_image?.presigned_url ||
    normalized?.payload?.rectified_image_url ||
    normalized?.payload?.artifacts?.rectified_image?.presigned_url ||
    normalized?.imageDataUrl;

  const resolvedImageSrc = !imgBroken
    ? imageUrl
    : normalized?.imageDataUrl || imageUrl;

  const jsonText = (() => {
    try {
      return JSON.stringify(result, null, 2);
    } catch {
      return String(result);
    }
  })();

  const getItemLabel = item =>
    item?.menu?.menu_name_en ||
    item?.menu?.menu_name_ko ||
    item?.menu_name_en ||
    item?.menu_name_ko ||
    "(no name)";

  return (
    <div className="ai-result-root">

      <button
        className="rp-back-btn"
        onClick={onRestart}
      >
        Analyze again
      </button>

      {/* Image + overlay */}
      <div className="ai-image-wrap">
        {resolvedImageSrc ? (
          <img
            className="rp-image"
            src={resolvedImageSrc}
            alt="menu result"
            onLoad={e => {
              setImgSize({
                w: e.currentTarget.naturalWidth || 0,
                h: e.currentTarget.naturalHeight || 0
              });
            }}
            onError={() => setImgBroken(true)}
          />
        ) : (
          <p className="rp-empty">No result image</p>
        )}

        <PolygonOverlay
          items={items}
          imgSize={imgSize}
          onSelectItem={setSelectedItem}
        />
      </div>

      {/* Modal */}
      {selectedItem && (
        <MenuDetailModal
          item={selectedItem}
          onClose={() => setSelectedItem(null)}
        />
      )}

      {/* Menu list */}
      {Array.isArray(items) &&
        items.length > 0 && (
          <div className="rp-menu-section">
            <h3 className="rp-menu-title">Detected menus</h3>

            <div className="rp-menu-grid">
              {items.map((it, idx) => (
                <div
                  key={
                    it?.id ||
                    it?.item_id ||
                    idx
                  }
                  className="rp-menu-card"
                >
                  <div className="rp-menu-name">
                    {getItemLabel(it)}
                  </div>

                  <button
                    onClick={() =>
                      setSelectedItem(it)
                    }
                    className="rp-menu-btn"
                  >
                    View details
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

      {/* Debug JSON */}
      <div className="rp-json-wrap">
        <h3 className="rp-json-title">Result JSON</h3>
        <pre className="rp-json-pre">{jsonText}</pre>
      </div>
    </div>
  );
}
