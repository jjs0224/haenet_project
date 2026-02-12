import { useEffect, useRef, useState } from "react";
import { ReviewAPI } from "../../api/reviewApi";
import { useNavigate } from "react-router-dom";
import CaptureFlow from "../../components/camera/CaptureFlow";
import styles from "./ReviewCreate.module.css";

export default function ReviewCreateInline({ onCreated }) {
  const navigate = useNavigate();

  // Step1
  const [receiptFile, setReceiptFile] = useState(null);
  const [receiptPreviewUrl, setReceiptPreviewUrl] = useState(null);
  const [receiptId, setReceiptId] = useState(null); // ✅ 운영에서는 job_id를 receipt_id처럼 사용
  const [extracted, setExtracted] = useState(null);
  const [menuList, setMenuList] = useState([]);
  const [menuConfirmed, setMenuConfirmed] = useState(false);

  // camera toggle
  const [showCamera, setShowCamera] = useState(false);

  // Step2
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [rating, setRating] = useState(5);

  const [images, setImages] = useState([]);
  const [previewUrls, setPreviewUrls] = useState([]);

  const receiptInputRef = useRef(null);
  const imageInputRef = useRef(null);

  const [loadingVerify, setLoadingVerify] = useState(false);
  const [loadingCreate, setLoadingCreate] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => {
    previewUrls.forEach((u) => URL.revokeObjectURL(u));
    const next = images.map((f) => URL.createObjectURL(f));
    setPreviewUrls(next);
    return () => next.forEach((u) => URL.revokeObjectURL(u));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [images]);

  // ✅ extracted 응답이 환경/버전에 따라 구조가 달라도 UI가 깨지지 않도록 정규화
  const normalizeExtracted = (raw) => {
    if (!raw || typeof raw !== "object") return null;

    const store = raw.store && typeof raw.store === "object" ? raw.store : {};

    const store_name =
      raw.store_name ||
      store.store_name ||
      store.name_ko ||
      store.name ||
      raw.storeName ||
      "";

    const store_name_en =
      raw.store_name_en ||
      store.store_name_en ||
      store.name_en ||
      raw.storeNameEn ||
      "";

    const coords = raw.coords || store.coords || null;

    // menu_en: 배열/문자열/객체배열 다 대응
    let menu_en = raw.menu_en;
    if (!menu_en && Array.isArray(raw.menu)) {
      menu_en = raw.menu
        .map((m) => (m && typeof m === "object" ? m.name_en : null))
        .filter(Boolean);
    }

    return {
      ...raw,
      store_name,
      store_name_en,
      coords,
      menu_en,
    };
  };

  const resetVerifyState = () => {
    setReceiptId(null);
    setExtracted(null);
    setMenuList([]);
    setMenuConfirmed(false);
    setMsg("");
    setErr("");
  };

  const hardResetReceiptInputs = () => {
    setReceiptFile(null);
    if (receiptPreviewUrl) URL.revokeObjectURL(receiptPreviewUrl);
    setReceiptPreviewUrl(null);
    setShowCamera(false);
    if (receiptInputRef.current) receiptInputRef.current.value = "";
  };

  // ✅ 핵심 수정: verifyReceipt(202 job) → waitReceiptJob(DONE payload) → extracted 사용
  const verify = async () => {
    setErr("");
    setMsg("");
    if (!receiptFile) return setErr("Please select the image of the receipt");

    setLoadingVerify(true);
    try {
      // 1) enqueue (보통 202 + job_id)
      const r = await ReviewAPI.verifyReceipt(receiptFile);
      const jobId = r?.data?.job_id || r?.data?.receipt_id || r?.data?.id;

      if (!jobId) throw new Error("verify response has no job_id");

      setReceiptId(jobId);
      setMsg("Receipt verification queued. Checking result...");

      // 2) poll until DONE/FAILED
      const res = await ReviewAPI.waitReceiptJob(jobId, {
        intervalMs: 2000,
        maxAttempts: 90,
      });

      const status = res?.data?.status;
      if (status !== "DONE") {
        const emsg =
          res?.data?.error?.message ||
          res?.data?.detail ||
          res?.data?.error ||
          "Receipt authentication failed";
        throw new Error(emsg);
      }

      // 3) DONE payload: extracted / final / payload 등 방어적으로 지원
      const rawExt =
        res?.data?.extracted ||
        res?.data?.final ||
        res?.data?.payload ||
        null;

      const ext = normalizeExtracted(rawExt);

      // coords 체크 (ext.coords 또는 ext.store.coords)
      const coords = ext?.coords;
      if (!coords || coords.x == null || coords.y == null) {
        alert("Please attach the receipt with the store address again");

        // reset
        resetVerifyState();
        hardResetReceiptInputs();
        setLoadingVerify(false);
        return;
      }

      setExtracted(ext);

      // menu_en parsing
      if (ext?.menu_en) {
        const raw = ext.menu_en;
        const parsed = Array.isArray(raw)
          ? raw.map((m) => String(m).replace(/["[\]]/g, "").trim())
          : String(raw)
              .split(",")
              .map((m) => m.replace(/["[\]]/g, "").trim());
        setMenuList(parsed.filter(Boolean));
      }

      setMsg("Receipt certified. Please check the menu.");
    } catch (e) {
      // ✅ axiosInstance 인터셉터에서 Error로 변환해서 던지므로 e.response 접근하면 안 됨
      setErr(e?.message || "Receipt authentication failed");
      resetVerifyState();
    } finally {
      setLoadingVerify(false);
    }
  };

  const confirmMenu = () => {
    setMenuConfirmed(true);
    setMsg("Checked the menu. Please write a review.");
  };

  const cancelMenu = () => {
    resetVerifyState();
    hardResetReceiptInputs();
  };

  const removeMenu = (idx) => {
    setMenuList((prev) => prev.filter((_, i) => i !== idx));
  };

  const onPickImages = (e) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;

    setErr("");
    setMsg("");

    setImages((prev) => {
      const merged = [...prev, ...files];
      if (merged.length > 3) {
        setErr("Upload up to three images.");
        return prev;
      }
      return merged;
    });

    if (imageInputRef.current) imageInputRef.current.value = "";
  };

  const removeImage = (idx) => {
    setImages((prev) => prev.filter((_, i) => i !== idx));
  };

  const create = async () => {
    setErr("");
    setMsg("");

    if (!receiptId) return setErr("Please verify the receipt first");
    if (!title.trim()) return setErr("Please enter the title");
    if (!content.trim()) return setErr("Please enter the content");
    if (images.length > 3) return setErr("upload up to three images.");

    setLoadingCreate(true);
    try {
      // ⚠️ 기존 프론트 API는 /review/create 로 전송하고 있음(너 프로젝트 기준 유지)
      const r = await ReviewAPI.createFromReceipt({
        receipt_id: receiptId,                 // ✅ job_id를 그대로 receipt_id로 사용
        title,
        content,
        rating,
        menu_name: JSON.stringify(menuList),
        images,
      });

      setMsg("Completion of review creation");
      navigate("/review?mine=true");
      onCreated?.(r.data);

      // reset all
      hardResetReceiptInputs();
      resetVerifyState();
      setTitle("");
      setContent("");
      setRating(5);
      setImages([]);
    } catch (e) {
      setErr(e?.message || "Failed to create review");
    } finally {
      setLoadingCreate(false);
    }
  };

  return (
    <div className={styles.reviewCreateContainer}>
      {loadingVerify && (
        <div className={styles.loadingOverlay}>
          <div className={styles.loadingBox}>
            <div className={styles.loadingSpinner} />
            <p className={styles.loadingText}>Detecting Receipt...</p>
          </div>
        </div>
      )}

      <h2 className={styles.reviewCreateTitle}>Create Review</h2>

      {/* Step 1 */}
      {!receiptId && (
        <div className={styles.stepSection}>
          <div className={styles.stepHeader}>Verify Receipt</div>

          {showCamera && !receiptFile && (
            <CaptureFlow
              onDone={(file) => {
                setReceiptFile(file);
                if (receiptPreviewUrl) URL.revokeObjectURL(receiptPreviewUrl);
                setReceiptPreviewUrl(URL.createObjectURL(file));
                setShowCamera(false);
              }}
            />
          )}

          {!showCamera && (
            <>
              <div className={styles.receiptUpload}>
                <input
                  ref={receiptInputRef}
                  type="file"
                  accept="image/*"
                  disabled={loadingVerify}
                  onChange={(e) => {
                    const f = e.target.files?.[0] || null;
                    setReceiptFile(f);
                    if (receiptPreviewUrl) URL.revokeObjectURL(receiptPreviewUrl);
                    setReceiptPreviewUrl(f ? URL.createObjectURL(f) : null);
                  }}
                  className={styles.fileInput}
                />

                <button
                  type="button"
                  onClick={() => {
                    setErr("");
                    setMsg("");
                    setShowCamera(true);
                  }}
                  disabled={loadingVerify}
                  className={styles.btnCamera}
                  title="Open Camera"
                >
                  📷
                </button>

                <button
                  onClick={verify}
                  disabled={loadingVerify}
                  className={styles.btnPrimary}
                >
                  {loadingVerify ? "⏳" : "✔"}
                </button>
              </div>

              {receiptPreviewUrl && (
                <div className={styles.receiptPreview}>
                  <img
                    src={receiptPreviewUrl}
                    alt="Preview Receipts"
                    className={styles.receiptPreviewImage}
                  />
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* Step 2 */}
      {receiptId && extracted && (
        <div className={styles.stepSection}>
          <div className={styles.stepHeader}>Confirm Receipt Details</div>
          <p>
            {extracted.store_name} / {extracted.store_name_en}
          </p>

          <div className={styles.menuConfirmSection}>
            {!menuConfirmed && (
              <p className={styles.menuConfirmText}>Please only select your menu</p>
            )}

            <div className={styles.menuList}>
              {menuList.length > 0 ? (
                menuList.map((menu, idx) => (
                  <div key={idx} className={styles.menuItem}>
                    <span className={styles.menuIcon}>🍽️</span>
                    <span className={styles.menuName}>{menu}</span>
                    {!menuConfirmed && (
                      <button
                        type="button"
                        onClick={() => removeMenu(idx)}
                        className={styles.btnRemoveMenu}
                        title="Delete Menu"
                      >
                        ×
                      </button>
                    )}
                  </div>
                ))
              ) : (
                <p className={styles.menuConfirmText}>There's no menu.</p>
              )}
            </div>

            {!menuConfirmed && (
              <div className={styles.menuConfirmButtons}>
                <button
                  onClick={confirmMenu}
                  disabled={menuList.length === 0}
                  className={styles.btnConfirm}
                >
                  Confirm
                </button>
                <button onClick={cancelMenu} className={styles.btnCancel}>
                  Cancel
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Step 3 */}
      {receiptId && menuConfirmed && (
        <div className={styles.stepSection}>
          <div className={styles.stepHeader}>Create a review</div>

          <div className={styles.reviewForm}>
            <div className={styles.formGroup}>
              <label className={styles.formLabel}>Title</label>
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Enter review title"
                className={styles.formInput}
              />
            </div>

            <div className={styles.formGroup}>
              <label className={styles.formLabel}>Content</label>
              <textarea
                value={content}
                onChange={(e) => setContent(e.target.value)}
                placeholder="Enter review content"
                rows={6}
                className={styles.formTextarea}
              />
            </div>

            <div className={styles.formGroup}>
              <label className={styles.formLabel}>Rating</label>
              <div className={styles.ratingSelect}>
                {[1, 2, 3, 4, 5].map((n) => (
                  <span
                    key={n}
                    onClick={() => setRating(n)}
                    className={`${styles.star} ${n <= rating ? styles.active : ""}`}
                  >
                    ★
                  </span>
                ))}
              </div>
            </div>

            <div className={styles.formGroup}>
              <label className={styles.formLabel}>추가 이미지 (max 3)</label>
              <input
                ref={imageInputRef}
                type="file"
                accept="image/*"
                multiple
                onChange={onPickImages}
                disabled={images.length >= 3}
                className={styles.fileInput}
              />
              <div className={styles.imageCount}>Additional Images {images.length}/3</div>

              {previewUrls.length > 0 && (
                <div className={styles.imagePreviewList}>
                  {previewUrls.map((url, idx) => (
                    <div key={idx} className={styles.imagePreviewItem}>
                      <img src={url} alt={`preview-${idx}`} className={styles.previewImage} />
                      <button
                        type="button"
                        onClick={() => removeImage(idx)}
                        className={styles.btnRemoveImage}
                        title="Delete"
                      >
                        ×
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <button onClick={create} disabled={loadingCreate} className={styles.btnSubmit}>
              {loadingCreate ? "Creating..." : "Save"}
            </button>
          </div>
        </div>
      )}

      {msg && <div className={`${styles.message} ${styles.success}`}>{msg}</div>}
      {err && <div className={`${styles.message} ${styles.error}`}>{err}</div>}
    </div>
  );
}
