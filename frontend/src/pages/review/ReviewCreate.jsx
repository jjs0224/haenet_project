import { useEffect, useRef, useState } from "react";
import { ReviewAPI } from "../../api/reviewApi";
import { useNavigate } from "react-router-dom";
import CaptureFlow from "../../components/camera/CaptureFlow"; // ✅ add
import styles from "./ReviewCreate.module.css";

export default function ReviewCreateInline({ onCreated }) {
  const navigate = useNavigate();

  // Step1
  const [receiptFile, setReceiptFile] = useState(null);
  const [receiptPreviewUrl, setReceiptPreviewUrl] = useState(null);
  const [receiptId, setReceiptId] = useState(null);
  const [extracted, setExtracted] = useState(null);
  const [menuList, setMenuList] = useState([]);
  const [menuConfirmed, setMenuConfirmed] = useState(false);

  // ✅ camera toggle
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

    const verify = async () => {
        setErr("");
        setMsg("");
        if (!receiptFile) return setErr("Please select the image of the receipt");

    setLoadingVerify(true);
    try {
      const r = await ReviewAPI.verifyReceipt(receiptFile);
      console.log("rrrrr :: ", r)
      const ext = r.data?.extracted || null;
      console.log("ext :: ", ext)

      const coords = ext?.coords;
      if (!coords || coords.x == null || coords.y == null) {
        alert("Please attach the receipt with the store address again");

        // reset
        setReceiptFile(null);
        if (receiptPreviewUrl) URL.revokeObjectURL(receiptPreviewUrl);
        setReceiptPreviewUrl(null);
        setReceiptId(null);
        setExtracted(null);
        setMenuList([]);
        setShowCamera(false);
        if (receiptInputRef.current) receiptInputRef.current.value = "";
        setLoadingVerify(false);
        return;
      }

      setReceiptId(r.data?.receipt_id);
      setExtracted(ext);

      if (ext?.menu_en) {
        const raw = ext.menu_en;
        const parsed = Array.isArray(raw)
          ? raw.map((m) => String(m).replace(/["[\]]/g, "").trim())
          : raw.split(",").map((m) => m.replace(/["[\]]/g, "").trim());
        setMenuList(parsed.filter(Boolean));
      }

      setMsg("Receipt certified. Please check the menu.");
    } catch (e) {
      setErr(
        e?.response?.data?.detail ||
          e?.message ||
          "Receipt authentication failed"
      );
    } finally {
      setLoadingVerify(false);
    }
  };

    const confirmMenu = () => {
        setMenuConfirmed(true);
        setMsg("Checked the menu. Please write a review.");
    };

  const cancelMenu = () => {
    setReceiptId(null);
    setExtracted(null);
    setMenuList([]);
    setReceiptFile(null);
    if (receiptPreviewUrl) URL.revokeObjectURL(receiptPreviewUrl);
    setReceiptPreviewUrl(null);
    setMenuConfirmed(false);
    setShowCamera(false);
    setMsg("");
    setErr("");
    if (receiptInputRef.current) receiptInputRef.current.value = "";
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
      const r = await ReviewAPI.createFromReceipt({
        receipt_id: receiptId,
        title,
        content,
        rating,
        menu_name: JSON.stringify(menuList),
        images,
      });

      setMsg("Completion of review creation");
      navigate("/review?mine=true");
      onCreated?.(r.data);

      setReceiptFile(null);
      if (receiptPreviewUrl) URL.revokeObjectURL(receiptPreviewUrl);
      setReceiptPreviewUrl(null);
      setReceiptId(null);
      setExtracted(null);
      setMenuList([]);
      setMenuConfirmed(false);
      setShowCamera(false);
      setTitle("");
      setContent("");
      setRating(5);
      setImages([]);
    } catch (e) {
      setErr(e?.response?.data?.detail || e?.message || "Failed to create review");
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

          {/* ✅ camera page */}
          {showCamera && !receiptFile && (
            <CaptureFlow
              onDone={(file) => {
                setReceiptFile(file);
                if (receiptPreviewUrl) URL.revokeObjectURL(receiptPreviewUrl);
                setReceiptPreviewUrl(URL.createObjectURL(file));
                setShowCamera(false); // back to normal UI
              }}
            />
          )}

          {/* ✅ normal upload UI (your original) */}
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

                {/* ✅ new camera button beside check */}
                <button
                  type="button"
                  onClick={() => {
                    setErr("");
                    setMsg("");
                    setShowCamera(true);
                  }}
                  disabled={loadingVerify}
                  className={styles.btnCamera} // (or reuse btnPrimary if you want)
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

            {msg && (
                <div className={`${styles.message} ${styles.success}`}>
                    {msg}
                </div>
            )}
            {err && (
                <div className={`${styles.message} ${styles.error}`}>{err}</div>
            )}
        </div>
    );
}
