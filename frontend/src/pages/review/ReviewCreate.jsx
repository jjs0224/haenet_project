// src/features/review/ReviewCreate.jsx
// ✅ AWS 운영(큐/worker) 구조 대응: /verify(202 job_id) → job/{job_id} 폴링 → DONE 결과(extracted) 사용
// ⚠️ 프로젝트 폴더 구조에 따라 import 경로만 너 환경에 맞게 조정해줘.

import React, { useMemo, useState } from "react";
import ReviewAPI from "./reviewApi"; // 예: src/features/review/reviewApi.js

export default function ReviewCreate() {
  // ---- form fields ----
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [rating, setRating] = useState(5);
  const [menuNameOverride, setMenuNameOverride] = useState("");

  // receipt verify
  const [receiptFile, setReceiptFile] = useState(null);
  const [receiptJobId, setReceiptJobId] = useState(""); // 백엔드에서는 job_id를 receipt_id처럼 사용(ReceiptSessionService key)
  const [extracted, setExtracted] = useState(null);

  // review images (0~3)
  const [reviewImages, setReviewImages] = useState([]);

  // ui
  const [loadingVerify, setLoadingVerify] = useState(false);
  const [loadingSubmit, setLoadingSubmit] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  // ---- derived ----
  const coords = useMemo(() => {
    // extracted 구조가 store 중심이면 ext.store.coords
    // 혹시 ext.coords로 내려오는 케이스도 방어
    return extracted?.store?.coords || extracted?.coords || null;
  }, [extracted]);

  const storeName = extracted?.store?.name_ko || extracted?.store?.store_name || extracted?.store?.name || "";
  const storeAddr = extracted?.store?.address || extracted?.store?.store_address || "";
  const menuKo = Array.isArray(extracted?.menu) ? extracted.menu.map((m) => m?.name_ko).filter(Boolean) : [];

  // ---- handlers ----
  const resetVerifyState = () => {
    setReceiptJobId("");
    setExtracted(null);
  };

  const onPickReceipt = (e) => {
    const f = e.target.files?.[0] || null;
    setReceiptFile(f);
    resetVerifyState();
    setErr("");
    setMsg("");
  };

  const onPickReviewImages = (e) => {
    const files = Array.from(e.target.files || []);
    setReviewImages(files.slice(0, 3)); // 0~3장
  };

  // ✅ 핵심: verifyReceipt -> waitReceiptJob 폴링
  const onVerifyReceipt = async () => {
    setErr("");
    setMsg("");

    if (!receiptFile) {
      setErr("Please select the image of the receipt");
      return;
    }

    setLoadingVerify(true);
    try {
      // 1) enqueue (202)
      const r = await ReviewAPI.verifyReceipt(receiptFile);
      const jobId = r?.data?.job_id;
      if (!jobId) throw new Error("verify response has no job_id");

      setReceiptJobId(jobId);
      setMsg("Receipt verification queued. Checking result...");

      // 2) poll until DONE / FAILED
      const res = await ReviewAPI.waitReceiptJob(jobId, {
        intervalMs: 2000,
        maxAttempts: 90, // 약 3분
      });

      const status = res?.data?.status;
      if (status !== "DONE") {
        const emsg = res?.data?.error?.message || res?.data?.error || "receipt verify failed";
        throw new Error(emsg);
      }

      // 3) DONE payload
      const ext = res?.data?.extracted || null;
      setExtracted(ext);

      const c = ext?.store?.coords || ext?.coords;
      if (!c || c.x == null || c.y == null) {
        // 여기서 너가 말한 문구가 뜨던 곳
        // 이제는 "진짜로 coords가 없는 경우"에만 뜸
        alert("Please attach the receipt with the store address again");
        return;
      }

      setMsg("Receipt verified successfully ✅");
    } catch (e) {
      setErr(e?.message || String(e));
      setMsg("");
      // 실패 시 verify 결과 초기화
      resetVerifyState();
    } finally {
      setLoadingVerify(false);
    }
  };

  const onSubmitReview = async () => {
    setErr("");
    setMsg("");

    if (!receiptJobId) {
      setErr("Please verify the receipt first.");
      return;
    }
    if (!title.trim()) {
      setErr("Please enter the title.");
      return;
    }
    if (!content.trim()) {
      setErr("Please enter the content.");
      return;
    }

    // coords가 꼭 필요 정책이면 여기서 막고, 아니면 허용해도 됨
    if (!coords || coords.x == null || coords.y == null) {
      setErr("No coordinates found. Please verify with a receipt that contains store address.");
      return;
    }

    setLoadingSubmit(true);
    try {
      // 백엔드 create_review_from_receipt는 receipt_id로 session을 찾음
      // 너희 구조는 job_id == receipt_id 로 저장하는 형태라서 receiptJobId 그대로 넘기면 됨
      const resp = await ReviewAPI.createReviewFromReceipt({
        receipt_id: receiptJobId,
        title: title.trim(),
        content: content.trim(),
        rating: Number(rating),
        menu_name_override: menuNameOverride?.trim() ? menuNameOverride.trim() : null,
        images: reviewImages, // 0~3
      });

      setMsg(`Review created ✅ (id: ${resp?.data?.review_id ?? "-"})`);

      // reset form (원하면 유지해도 됨)
      setTitle("");
      setContent("");
      setRating(5);
      setMenuNameOverride("");
      setReceiptFile(null);
      setReviewImages([]);
      resetVerifyState();
    } catch (e) {
      setErr(e?.message || String(e));
    } finally {
      setLoadingSubmit(false);
    }
  };

  return (
    <div style={{ maxWidth: 880, margin: "0 auto", padding: 16 }}>
      <h2 style={{ marginBottom: 12 }}>Create Review</h2>

      {err && (
        <div style={{ background: "#ffe6e6", padding: 12, borderRadius: 8, marginBottom: 10 }}>
          <b>Error</b>
          <div>{err}</div>
        </div>
      )}
      {msg && (
        <div style={{ background: "#e9ffe6", padding: 12, borderRadius: 8, marginBottom: 10 }}>
          <b>Info</b>
          <div>{msg}</div>
        </div>
      )}

      {/* 1) Receipt Verify */}
      <section style={{ border: "1px solid #ddd", borderRadius: 10, padding: 14, marginBottom: 16 }}>
        <h3 style={{ marginTop: 0 }}>1) Receipt Verification</h3>

        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <input type="file" accept="image/*" onChange={onPickReceipt} />
          <button type="button" onClick={onVerifyReceipt} disabled={loadingVerify || !receiptFile}>
            {loadingVerify ? "Verifying..." : "Verify Receipt"}
          </button>

          {receiptJobId && (
            <span style={{ fontSize: 12, color: "#666" }}>
              job_id: <code>{receiptJobId}</code>
            </span>
          )}
        </div>

        {/* extracted preview */}
        {extracted && (
          <div style={{ marginTop: 14, padding: 12, borderRadius: 8, background: "#fafafa" }}>
            <div style={{ marginBottom: 6 }}>
              <b>Store</b>: {storeName || "-"}
            </div>
            <div style={{ marginBottom: 6 }}>
              <b>Address</b>: {storeAddr || "-"}
            </div>
            <div style={{ marginBottom: 6 }}>
              <b>Coords</b>: {coords ? `${coords.x}, ${coords.y}` : "-"}
            </div>
            <div>
              <b>Menu(KO)</b>: {menuKo.length ? menuKo.join(", ") : "-"}
            </div>
          </div>
        )}
      </section>

      {/* 2) Review Form */}
      <section style={{ border: "1px solid #ddd", borderRadius: 10, padding: 14 }}>
        <h3 style={{ marginTop: 0 }}>2) Review</h3>

        <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: 10 }}>
          <label>
            <div style={{ fontSize: 12, color: "#666", marginBottom: 4 }}>Title</div>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="title"
              style={{ width: "100%", padding: 10, borderRadius: 8, border: "1px solid #ccc" }}
            />
          </label>

          <label>
            <div style={{ fontSize: 12, color: "#666", marginBottom: 4 }}>Content</div>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="content"
              rows={6}
              style={{ width: "100%", padding: 10, borderRadius: 8, border: "1px solid #ccc" }}
            />
          </label>

          <label>
            <div style={{ fontSize: 12, color: "#666", marginBottom: 4 }}>Rating (1~5)</div>
            <input
              type="number"
              min={1}
              max={5}
              value={rating}
              onChange={(e) => setRating(e.target.value)}
              style={{ width: 120, padding: 10, borderRadius: 8, border: "1px solid #ccc" }}
            />
          </label>

          <label>
            <div style={{ fontSize: 12, color: "#666", marginBottom: 4 }}>
              Menu Name Override (optional)
            </div>
            <input
              value={menuNameOverride}
              onChange={(e) => setMenuNameOverride(e.target.value)}
              placeholder='ex) "김치찌개, 공기밥"'
              style={{ width: "100%", padding: 10, borderRadius: 8, border: "1px solid #ccc" }}
            />
          </label>

          <label>
            <div style={{ fontSize: 12, color: "#666", marginBottom: 4 }}>Review Images (0~3)</div>
            <input type="file" accept="image/*" multiple onChange={onPickReviewImages} />
            {reviewImages.length > 0 && (
              <div style={{ fontSize: 12, color: "#666", marginTop: 6 }}>
                selected: {reviewImages.map((f) => f.name).join(", ")}
              </div>
            )}
          </label>

          <button
            type="button"
            onClick={onSubmitReview}
            disabled={loadingSubmit || !receiptJobId}
            style={{
              padding: "12px 14px",
              borderRadius: 10,
              border: "1px solid #222",
              cursor: loadingSubmit || !receiptJobId ? "not-allowed" : "pointer",
            }}
          >
            {loadingSubmit ? "Submitting..." : "Create Review"}
          </button>

          {!receiptJobId && (
            <div style={{ fontSize: 12, color: "#999" }}>
              * You must verify the receipt first.
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
