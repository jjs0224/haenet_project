import React, { useMemo, useState, useEffect } from "react";
import { MenuAPI } from "../../api/menuApi";
import ResultPage from "../../pages/menuscan/ResultPage";

/**
 * 백엔드 응답 형태 방어적 표준화
 * - router response_model: { job_id, upload_type, result }
 * - result 내부: { final, rectified_image: { mime, base64 }, run_id, meta? }
 */
function normalizeBackendPayload(raw) {
  const root = raw?.data ?? raw;

  // 1) router wrapper가 있으면 result로 들어감
  const payload = root?.result ?? root;

  // 2) 서비스가 반환한 형태
  const finalObj = payload?.final ?? payload?.final_obj ?? payload?.final_json ?? payload;

  // 3) rectified 이미지 추출
  const rectified = payload?.rectified_image ?? payload?.rectified ?? null;
  const base64 = rectified?.base64 ?? null;
  const mime = rectified?.mime ?? "image/jpeg";
  const imageDataUrl = base64 ? `data:${mime};base64,${base64}` : null;

  // 4) run_id / job_id
  const runId = payload?.run_id ?? root?.job_id ?? root?.run_id ?? null;

  return { raw: root, payload, final: finalObj, imageDataUrl, runId };
}

const LS_KEY = "haenet_user_profile_json";

export default function MenuUploadInline() {
  const [file, setFile] = useState(null);
  const [msg, setMsg] = useState("");
  const [rawRes, setRawRes] = useState(null);
  const [loading, setLoading] = useState(false);

  // ✅ 추가: user_profile JSON 입력(문자열)
  const [profileText, setProfileText] = useState("");

  useEffect(() => {
    // 새로고침 후에도 입력 유지(편의)
    const saved = localStorage.getItem(LS_KEY);
    if (saved) setProfileText(saved);
  }, []);

  const normalized = useMemo(() => (rawRes ? normalizeBackendPayload(rawRes) : null), [rawRes]);

  const parseProfile = () => {
    const t = (profileText || "").trim();
    if (!t) return null; // 미전송 → 백엔드 default profile 사용

    try {
      const obj = JSON.parse(t);
      if (!obj || typeof obj !== "object" || Array.isArray(obj)) {
        throw new Error("user_profile은 JSON object 형태여야 해");
      }
      return obj;
    } catch (e) {
      throw new Error(`user_profile JSON 파싱 실패: ${e?.message || e}`);
    }
  };

  const onUpload = async () => {
    if (!file) return setMsg("이미지를 선택해줘");
    setMsg("");
    setRawRes(null);
    setLoading(true);

    try {
      const profileObj = parseProfile();

      // ✅ 저장(파싱 성공 or 빈 값)
      localStorage.setItem(LS_KEY, (profileText || "").trim());

      const r = await MenuAPI.uploadMenu(file, profileObj);

      setRawRes(r);

      // meta.profile_source가 있으면 메시지 개선(없어도 기존 메시지 유지)
      const profileSource = r?.data?.result?.meta?.profile_source;
      if (profileSource === "default") {
        setMsg("✅ 메뉴 분석 완료 (프로필 미제공 → 기본 프로필로 분석됨)");
      } else if (profileSource === "provided") {
        setMsg("✅ 메뉴 분석 완료 (사용자 프로필 적용됨)");
      } else {
        setMsg("✅ 메뉴 분석 완료");
      }
    } catch (e) {
      setMsg(`❌ ${e?.response?.data?.detail || e?.message || "업로드 실패"}`);
    } finally {
      setLoading(false);
    }
  };

  const onClearProfile = () => {
    setProfileText("");
    localStorage.removeItem(LS_KEY);
    setMsg("프로필 입력을 초기화했어 (다음 업로드는 기본 프로필로 분석됨)");
  };

  if (normalized) {
    // ResultPage는 "원본응답"을 그대로 받아서 내부에서 표준화하도록 구성
    return (
      <div>
        <div style={{ marginBottom: 12, display: "flex", gap: 8 }}>
          <button onClick={() => setRawRes(null)}>다시 업로드</button>
          <button onClick={() => setMsg("")}>메시지 지우기</button>
        </div>
        {msg && <div style={{ marginBottom: 12 }}>{msg}</div>}
        <ResultPage result={normalized.raw?.data ?? normalized.raw} />
      </div>
    );
  }

  return (
    <div style={{ border: "1px solid #ddd", padding: 12, borderRadius: 8 }}>
      <h3 style={{ marginTop: 0 }}>메뉴 이미지 업로드</h3>

      <div style={{ display: "grid", gap: 10 }}>
        <div>
          <div style={{ fontSize: 13, color: "#444", marginBottom: 6 }}>
            1) 이미지 선택
          </div>
          <input
            type="file"
            accept="image/*"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
          />
        </div>

        <div>
          <div style={{ fontSize: 13, color: "#444", marginBottom: 6 }}>
            2) 사용자 프로필(JSON, 선택)
          </div>
          <textarea
            value={profileText}
            onChange={(e) => setProfileText(e.target.value)}
            placeholder={`예시:
{
  "allergy_tags": ["ALG_PEANUT", "ALG_CRUSTACEANS"],
  "avoid_foods": ["땅콩", "새우", "돼지고기"],
  "religion": "islam_halal"
}`}
            rows={8}
            style={{
              width: "100%",
              fontFamily: "monospace",
              fontSize: 12,
              padding: 10,
              borderRadius: 8,
              border: "1px solid #ddd",
            }}
          />
          <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
            <button onClick={onClearProfile} disabled={loading}>
              프로필 초기화
            </button>
            <div style={{ fontSize: 12, color: "#666", alignSelf: "center" }}>
              비워두면 백엔드가 기본 프로필(알러지/회피/종교 없음)로 분석해.
            </div>
          </div>
        </div>

        <div>
          <button onClick={onUpload} disabled={loading} style={{ marginRight: 8 }}>
            {loading ? "분석중..." : "업로드/분석"}
          </button>
          {msg && <span style={{ marginLeft: 8 }}>{msg}</span>}
        </div>
      </div>
    </div>
  );
}
