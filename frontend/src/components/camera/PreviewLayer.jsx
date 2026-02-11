export default function PreviewLayer({
  previewUrl,
  onRetry,
  onConfirm
}) {
  return (
    <div className="preview-root">
      <img
        src={previewUrl}
        alt="preview"
        className="preview-image"
      />

      <div className="preview-controls">
        <button onClick={onRetry}>
          다시 촬영
        </button>

        <button onClick={onConfirm}>
          확인
        </button>
      </div>
    </div>
  );
}