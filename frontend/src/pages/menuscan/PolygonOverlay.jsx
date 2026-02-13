import React, { useMemo } from "react";
// import "./PolygonOverlay.css";
import './menuscan.css';

/**
 * [final_translated 기준 + 하위호환]
 * - poly: item.poly  (fallback: item.match.poly)
 * - label: item.menu_name_en (fallback: item.menu.menu_name_en -> ko)
 * - color: risk_difficulty (3=gray, 2=red, 1=orange, 0=green)
 *
 * 목표:
 * - poly 박스 표시 (risk_difficulty 기반 색상)
 * - 박스 안에 "한 줄"로, 박스 높이에 맞게 텍스트 자동 맞춤
 * - 클릭 시 onSelectItem(item)로 Modal 연동
 */

function extractPoly(item) {
  const poly = item?.poly ?? item?.match?.poly;

  if (!Array.isArray(poly)) return null;
  if (!poly.every((p) => Array.isArray(p) && p.length >= 2)) return null;

  return poly
    .map((p) => [Number(p[0]), Number(p[1])])
    .filter((p) => Number.isFinite(p[0]) && Number.isFinite(p[1]));
}

function clamp(v, min, max) {
  return Math.max(min, Math.min(max, v));
}

// stroke(hex) -> rgba
function hexToRgba(hex, alpha) {
  const h = String(hex || "").replace("#", "").trim();
  if (h.length !== 6) return `rgba(0,0,0,${alpha})`;
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function getLabel(item) {
  return (
    item?.menu_name_en ||
    item?.menu?.menu_name_en ||
    item?.menu_name_ko ||
    item?.menu?.menu_name_ko ||
    ""
  );
}

function riskDifficultyToKey(v) {
  const n = Number(v);
  if (n === 3) return "gray";
  if (n === 2) return "red";
  if (n === 1) return "orange";
  if (n === 0) return "green";
  return "gray";
}

function riskDifficultyToStroke(v) {
  const key = riskDifficultyToKey(v);
  if (key === "green") return "#16a34a";
  if (key === "orange") return "#f97316";
  if (key === "red") return "#ef4444";
  return "#9ca3af";
}

function centroid(poly) {
  const n = poly.length;
  const sx = poly.reduce((a, p) => a + p[0], 0);
  const sy = poly.reduce((a, p) => a + p[1], 0);
  return [sx / n, sy / n];
}

function getBBox(poly) {
  let minX = Infinity,
    minY = Infinity,
    maxX = -Infinity,
    maxY = -Infinity;

  for (const [x, y] of poly) {
    if (x < minX) minX = x;
    if (y < minY) minY = y;
    if (x > maxX) maxX = x;
    if (y > maxY) maxY = y;
  }

  return { minX, minY, maxX, maxY, w: maxX - minX, h: maxY - minY };
}

function estimateTextWidthPx(text, fontSize) {
  const s = String(text || "");
  const base = 0.56;
  let units = 0;

  for (const ch of s) {
    if (ch === " " || ch === "-") units += 0.30;
    else if (ch === ".") units += 0.22;
    else units += 1.0;
  }

  return units * base * fontSize;
}

function truncateToFit(text, availW, fontSize) {
  const s = String(text || "").trim();
  if (!s) return "";

  if (estimateTextWidthPx(s, fontSize) <= availW) return s;

  const ell = "…";
  if (estimateTextWidthPx(ell, fontSize) > availW) return "";

  // binary search for max length that fits with ellipsis
  let lo = 0;
  let hi = s.length;
  let best = "";

  while (lo <= hi) {
    const mid = Math.floor((lo + hi) / 2);
    const cand = s.slice(0, mid).trimEnd() + ell;
    if (estimateTextWidthPx(cand, fontSize) <= availW) {
      best = cand;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return best || ell;
}

function pickSingleLineTextAndFont(label, boxW, boxH) {
  const text = String(label || "").trim();
  if (!text) return { text: "", fs: 10 };

  // padding: 박스 내부 여백
  const padX = Math.max(6, boxW * 0.06);
  const padY = Math.max(4, boxH * 0.18);

  const availW = Math.max(0, boxW - padX * 2);
  const availH = Math.max(0, boxH - padY * 2);

  // "박스 높이에 딱 맞게" => height 기반으로 상한을 먼저 잡음
  const maxByH = availH / 1.05; // line-height 여유 거의 없이
  const maxFont = clamp(Math.floor(maxByH), 10, 28);
  const minFont = 9;

  for (let fs = maxFont; fs >= minFont; fs -= 1) {
    const fitted = truncateToFit(text, availW, fs);
    if (fitted) return { text: fitted, fs };
  }

  // 최후: 최소 폰트 + truncate
  return { text: truncateToFit(text, availW, minFont), fs: minFont };
}

export default function PolygonOverlay({ items, imgSize, onSelectItem }) {
  const polygons = useMemo(() => {
    if (!Array.isArray(items)) return [];
    return items
      .map((item) => ({ item, poly: extractPoly(item) }))
      .filter((x) => Array.isArray(x.poly) && x.poly.length >= 3);
  }, [items]);

  const w = imgSize?.w || 0;
  const h = imgSize?.h || 0;
  if (!w || !h || polygons.length === 0) return null;

  return (
    <svg className="ms-po__svg" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
      {polygons.map(({ item, poly }, idx) => {
        const points = poly.map((p) => `${p[0]},${p[1]}`).join(" ");
        const bbox = getBBox(poly);
        const label = getLabel(item);

        const riskDifficulty = item?.risk_difficulty ?? item?.risk?.risk_difficulty ?? null;
        const colorKey = riskDifficultyToKey(riskDifficulty);
        const stroke = riskDifficultyToStroke(riskDifficulty);

        const { text: fittedText, fs } = pickSingleLineTextAndFont(label, bbox.w, bbox.h);
        const [cx, cy] = centroid(poly);

        return (
          <g
            key={item?.item_id || idx}
            className="ms-po__group"
            onClick={() => onSelectItem?.(item)}
          >
            <polygon
              className={`ms-po__poly ms-po__poly--${colorKey}`}
              points={points}
              style={{
                stroke,
                fill: hexToRgba(stroke, 0.84), // 내부 연하게 고정
                strokeWidth: 3,                // 테두리 진하게
                strokeOpacity: 0.95,
                fillOpacity: 1,
                strokeLinejoin: "round",
              }}
            />

            {fittedText && (
              <text
                className="ms-po__text"
                x={cx}
                y={cy}
                textAnchor="middle"
                dominantBaseline="middle"
                fontSize={fs}
                strokeWidth={Math.max(2, fs * 0.12)}
              >
                {fittedText}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}
