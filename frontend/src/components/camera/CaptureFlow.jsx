import LiveCameraLayer from "./LiveCameraLayer";
import './Capture.css';

export default function CaptureFlow({ onDone }) {
  
  const handleCapture = (file) => {
    if (!file) return;
    onDone(file);   // 촬영 즉시 부모로 전달
  };

  return (
    <div className="capture-root">
      <LiveCameraLayer
        onCapture={handleCapture}
      />
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
