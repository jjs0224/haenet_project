import { useEffect, useRef, useState } from "react";
import { ReviewAPI } from "../../api/reviewApi";
import { useNavigate } from "react-router-dom";
import CaptureFlow from "../../components/camera/CaptureFlow";
import styles from "./ReviewCreate.module.css";

export default function ReviewCreateInline({ onCreated }) {
    const navigate = useNavigate();

    // -------------------------
    // Step 1: Receipt
    // -------------------------
    const [receiptFile, setReceiptFile] = useState(null);
    const [receiptPreviewUrl, setReceiptPreviewUrl] = useState(null);
    const [receiptId, setReceiptId] = useState(null); // ✅ job_id를 receipt_id로 사용
    const [extracted, setExtracted] = useState(null);
    const [menuList, setMenuList] = useState([]);
    const [menuConfirmed, setMenuConfirmed] = useState(false);

    // camera toggle
    const [showCamera, setShowCamera] = useState(false);

    // menu selection
    const [selectedMenus, setSelectedMenus] = useState(new Set());

    // -------------------------
    // Step 2: Review
    // -------------------------
    const [title, setTitle] = useState("");
    const [content, setContent] = useState("");
    const [rating, setRating] = useState(5);

    // images (0~3)
    const [images, setImages] = useState([]);
    const [previewUrls, setPreviewUrls] = useState([]);

    // refs
    const receiptInputRef = useRef(null);
    const imageInputRef = useRef(null);

    // ui status
    const [loadingVerify, setLoadingVerify] = useState(false);
    const [loadingCreate, setLoadingCreate] = useState(false);
    const [msg, setMsg] = useState("");
    const [err, setErr] = useState("");

    // -------------------------
    // Preview URLs for review images
    // -------------------------
    useEffect(() => {
        previewUrls.forEach((u) => URL.revokeObjectURL(u));
        const next = images.map((f) => URL.createObjectURL(f));
        setPreviewUrls(next);

        return () => next.forEach((u) => URL.revokeObjectURL(u));
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [images]);

    // -------------------------
    // Helpers
    // -------------------------
    const resetReceiptFlow = () => {
        setReceiptFile(null);
        if (receiptPreviewUrl) URL.revokeObjectURL(receiptPreviewUrl);
        setReceiptPreviewUrl(null);

        setReceiptId(null);
        setExtracted(null);

        setMenuList([]);
        setMenuConfirmed(false);

        setShowCamera(false);

        if (receiptInputRef.current) receiptInputRef.current.value = "";
    };

    const parseMenus = (rawMenu) => {
        if (!rawMenu) return [];

        // Array
        if (Array.isArray(rawMenu)) {
            return rawMenu
                .map((m) =>
                    String(m)
                        .replace(/["[\]]/g, "")
                        .trim(),
                )
                .filter(Boolean);
        }

        // string (maybe JSON array string)
        if (typeof rawMenu === "string") {
            const s = rawMenu.trim();

            try {
                const j = JSON.parse(s);
                if (Array.isArray(j)) {
                    return j.map((m) => String(m).trim()).filter(Boolean);
                }
                return [String(j).trim()].filter(Boolean);
            } catch {
                return s
                    .split(",")
                    .map((m) => m.replace(/["[\]]/g, "").trim())
                    .filter(Boolean);
            }
        }

        // fallback
        return [String(rawMenu).trim()].filter(Boolean);
    };

    // coords 추출(구조가 달라도 최대한 잡아줌)
    const pickCoords = (ext) => {
        const candidate =
            ext?.coords ??
            ext?.store?.coords ??
            ext?.location ??
            ext?.store_location ??
            null;

        // object: {x,y}
        if (
            candidate &&
            typeof candidate === "object" &&
            !Array.isArray(candidate)
        ) {
            const x = candidate.x ?? candidate.lng ?? candidate.lon ?? null;
            const y = candidate.y ?? candidate.lat ?? null;
            return { x, y, raw: candidate };
        }

        // array: [x,y]
        if (Array.isArray(candidate)) {
            const x = candidate[0] ?? null;
            const y = candidate[1] ?? null;
            return { x, y, raw: candidate };
        }

        return { x: null, y: null, raw: candidate };
    };

    // -------------------------
    // Verify Receipt (핵심)
    // -------------------------
    const verify = async () => {
        setErr("");
        setMsg("");

        if (!receiptFile) {
            setErr("Please select the image of the receipt");
            return;
        }

        setLoadingVerify(true);

        try {
            // 1) enqueue (202) -> job_id 반환
            const r = await ReviewAPI.verifyReceipt(receiptFile);
            const jobId =
                r?.data?.job_id || r?.data?.receipt_id || r?.data?.id || null;

            if (!jobId) {
                throw new Error("No job_id returned");
            }

            // 2) poll until DONE/FAILED
            const jobRes = await ReviewAPI.waitReceiptJob(jobId);
            const status = jobRes?.data?.status;

            console.log("✅ jobRes status:", status);

            if (status !== "DONE") {
                const emsg =
                    jobRes?.data?.error?.message ||
                    jobRes?.data?.detail ||
                    "Receipt authentication failed";
                throw new Error(emsg);
            }

            // 3) DONE payload
            const ext = jobRes?.data?.extracted ?? null;

            console.log("✅ extracted keys:", ext ? Object.keys(ext) : null);
            console.log("✅ extracted:", ext);

            if (!ext) {
                throw new Error("No extracted payload returned");
            }

            // receipt_id == jobId 로 사용
            setReceiptId(jobId);
            setExtracted(ext);

            // 4) coords validate
            const { x, y, raw } = pickCoords(ext);

            console.log("coords raw:", raw);
            console.log("coords x,y:", x, y);

            if (x == null || y == null) {
                alert("Please attach the receipt with the store address again");
                resetReceiptFlow();
                return;
            }

            // 5) menus
            const rawMenu = ext?.menu_en ?? ext?.menu_name ?? ext?.menu ?? null;
            const parsedMenus = parseMenus(rawMenu);
            setMenuList(parsedMenus);
            // 기본적으로 모든 메뉴 선택
            setSelectedMenus(new Set(parsedMenus.map((_, i) => i)));

            setMsg("Receipt certified. Please check the menu.");
        } catch (e) {
            console.error("Receipt verification error:", e);

            // 401 에러 처리
            if (e?.response?.status === 401) {
                setErr("Session expired. Please log in again and try again.");
            } else {
                setErr(
                    e?.response?.data?.detail ||
                        e?.message ||
                        "Receipt authentication failed",
                );
            }
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
        setSelectedMenus(new Set());
        setReceiptFile(null);
        if (receiptPreviewUrl) URL.revokeObjectURL(receiptPreviewUrl);
        setReceiptPreviewUrl(null);
        setMenuConfirmed(false);
        setShowCamera(false);
        setMsg("");
        setErr("");
        if (receiptInputRef.current) receiptInputRef.current.value = "";
    };

    const toggleMenuSelection = (idx) => {
        setSelectedMenus((prev) => {
            const next = new Set(prev);
            if (next.has(idx)) {
                next.delete(idx);
            } else {
                next.add(idx);
            }
            return next;
        });
    };

    // -------------------------
    // Review images (0~3)
    // -------------------------
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

    // -------------------------
    // Create Review
    // -------------------------
    const create = async () => {
        setErr("");
        setMsg("");

        if (!receiptId) return setErr("Please verify the receipt first");
        if (!title.trim()) return setErr("Please enter the title");
        if (!content.trim()) return setErr("Please enter the content");
        if (images.length > 3) return setErr("upload up to three images.");

        setLoadingCreate(true);

        try {
            // 선택된 메뉴만 필터링
            const selectedMenuList = menuList.filter((_, i) => selectedMenus.has(i));
            const r = await ReviewAPI.createFromReceipt({
                receipt_id: receiptId,
                title,
                content,
                rating,
                menu_name: JSON.stringify(selectedMenuList),
                images,
            });

            setMsg("Completion of review creation");

            // navigate
            navigate("/review?mine=true");

            // callback
            onCreated?.(r.data);

            setReceiptFile(null);
            if (receiptPreviewUrl) URL.revokeObjectURL(receiptPreviewUrl);
            setReceiptPreviewUrl(null);
            setReceiptId(null);
            setExtracted(null);
            setMenuList([]);
            setSelectedMenus(new Set());
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

    // -------------------------
    // UI
    // -------------------------
    return (
        <div className={styles.reviewCreateContainer}>
            {loadingVerify && (
                <div className={styles.loadingOverlay}>
                    <div className={styles.loadingBox}>
                        <div className={styles.loadingSpinner} />
                        <p className={styles.loadingText}>
                            Detecting Receipt...
                        </p>
                    </div>
                </div>
            )}

            <h2 className={styles.reviewCreateTitle}>Create Review</h2>

            {/* Step 1 */}
            {!receiptId && (
                <div className={styles.stepSection}>
                    <div className={styles.stepHeader}>Verify Receipt</div>

                    {/* camera page */}
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

                    {/* normal upload UI (your original) */}
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
                                        // 기존 파일이 있으면 초기화
                                        if (receiptFile) {
                                            setReceiptFile(null);
                                            if (receiptPreviewUrl) URL.revokeObjectURL(receiptPreviewUrl);
                                            setReceiptPreviewUrl(null);
                                            if (receiptInputRef.current) receiptInputRef.current.value = "";
                                        }
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
                                    <div
                                        key={idx}
                                        className={`${styles.menuItem} ${!selectedMenus.has(idx) ? styles.deselected : ''}`}
                                        onClick={() => !menuConfirmed && toggleMenuSelection(idx)}
                                    >
                                        <span className={styles.menuIcon}>🍽️</span>
                                        <span className={styles.menuName}>{menu}</span>
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
                                <button
                                    onClick={cancelMenu}
                                    className={styles.btnCancel}
                                >
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
                            <label className={styles.formLabel}>
                                추가 이미지 (max 3)
                            </label>
                            <input
                                ref={imageInputRef}
                                type="file"
                                accept="image/*"
                                multiple
                                onChange={onPickImages}
                                disabled={images.length >= 3}
                                className={styles.fileInput}
                            />
                            <div className={styles.imageCount}>
                                Additional Images {images.length}/3
                            </div>

                            {previewUrls.length > 0 && (
                                <div className={styles.imagePreviewList}>
                                    {previewUrls.map((url, idx) => (
                                        <div
                                            key={idx}
                                            className={styles.imagePreviewItem}
                                        >
                                            <img
                                                src={url}
                                                alt={`preview-${idx}`}
                                                className={styles.previewImage}
                                            />
                                            <button
                                                type="button"
                                                onClick={() => removeImage(idx)}
                                                className={
                                                    styles.btnRemoveImage
                                                }
                                                title="Delete"
                                            >
                                                ×
                                            </button>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>

                        <button
                            onClick={create}
                            disabled={loadingCreate}
                            className={styles.btnSubmit}
                        >
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
