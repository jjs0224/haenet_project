import LiveCameraLayer from "./LiveCameraLayer";
import "./Capture.css";

export default function CaptureFlow({ onDone, onCancel }) {
  const handleCapture = (file) => {
    if (!file) return;
    onDone?.(file);
  };

  return (
    <div className="capture-root">
      <LiveCameraLayer
        onCapture={handleCapture}
        onFallback={() => {
          // 카메라 실패/업로드로 전환 요청 시 카메라 화면을 닫아줌
          onCancel?.();
        }}
      />
    </div>
  );
}