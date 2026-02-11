import { useEffect, useState } from "react";
import LiveCameraLayer from "./LiveCameraLayer";
import PreviewLayer from "./PreviewLayer";
import './Capture.css';

export default function CaptureFlow({ onDone }) {
  const [mode, setMode] = useState("camera");
  const [file, setFile] = useState(null);
  const [previewUrl, setPreviewUrl] = useState(null);

  /* =========================
     Preview entry
  ========================= */
  const enterPreview = f => {
    const url = URL.createObjectURL(f);
    setFile(f);
    setPreviewUrl(url);
    setMode("preview");
  };

  /* =========================
     Retry
  ========================= */
  const handleRetry = () => {
    cleanupPreview();
    setMode("camera");
  };

  /* =========================
     Confirm
  ========================= */
  const handleConfirm = () => {
    if (!file) return;
    onDone(file);
  };

  /* =========================
     Memory cleanup
  ========================= */
  const cleanupPreview = () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(null);
    setFile(null);
  };

  useEffect(() => cleanupPreview, []);

  /* =========================
     Render state machine
  ========================= */
  if (mode === "preview") {
    return (
      <PreviewLayer
        previewUrl={previewUrl}
        onRetry={handleRetry}
        onConfirm={handleConfirm}
      />
    );
  }

  // Camera-only 렌더링, 업로드 input 제거
  return (
    <div className="capture-root">
      <LiveCameraLayer onCapture={enterPreview} />
    </div>
  );
}

/* =============================
   Upload fallback screen (선택적)
============================= */
function UploadFallback({ onUpload, onBack }) {
  return (
    <div className="upload-fallback">
      <p>카메라를 사용할 수 없습니다</p>
      <input type="file" accept="image/*" onChange={onUpload} />
      <button onClick={onBack}>카메라로 돌아가기</button>
    </div>
  );
}