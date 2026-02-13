import { useEffect, useRef, useState } from "react";
import { CameraService } from "./CameraService";
import './LiveCamera.css';

const GUIDE_MESSAGES = {
  NOT_READY: "카메라 준비 중…",
  TOO_DARK: "조명이 부족합니다",
  BLURRY: "카메라가 흐립니다",
  SHAKING: "카메라를 고정하세요"
};

export default function LiveCameraLayer({
  onCapture,
  onFallback
}) {
  const videoRef = useRef(null);
  const cameraRef = useRef(null);
  const timerRef = useRef(null);

  const [guide, setGuide] = useState(null);
  const [error, setError] = useState(null);

  /* ===============================
     Camera lifecycle
  =============================== */

  useEffect(() => {
    let mounted = true;

    const init = async () => {
      try {
        const cam = new CameraService(
          videoRef.current
        );

        cameraRef.current = cam;

        await cam.start();

        if (!mounted) return;

        startGuideLoop();
      } catch (e) {
        setError("카메라 접근 실패");
        onFallback?.(e);
      }
    };

    const startGuideLoop = () => {
      timerRef.current = setInterval(() => {
        const cam = cameraRef.current;
        if (!cam) return;

        const result = cam.analyze();

        if (!result.ok) {
          setGuide(
            GUIDE_MESSAGES[result.reason] ||
              result.reason
          );
        } else {
          setGuide(null);
        }
      }, 250);
    };

    init();

    return () => {
      mounted = false;

      clearInterval(timerRef.current);

      cameraRef.current?.stop();
      cameraRef.current = null;
    };
  }, []);

  /* ===============================
     Capture handler
  =============================== */

  const handleCapture = async () => {
    const cam = cameraRef.current;
    if (!cam) return;

    try {
      const file = await cam.capture();
      onCapture(file);
    } catch {
      setGuide("촬영 실패 — 다시 시도");
    }
  };

  /* ===============================
     Render
  =============================== */

  if (error) {
    return (
      <div className="camera-error">
        <p>{error}</p>
        <button onClick={onFallback}>
          업로드 사용
        </button>
      </div>
    );
  }

  return (
    <div className="camera-root">
      <video
        ref={videoRef}
        className="camera-video"
        autoPlay
        playsInline
        muted
      />

      <GuideOverlay message={guide} />

      <button
        className="capture-button"
        onClick={handleCapture}
      >
        촬영
      </button>
    </div>
  );
}

/* ===================================
   Guide Overlay Component
=================================== */

function GuideOverlay({ message }) {
  return (
    <div className="guide-overlay">
      <div className="guide-frame" />

      {message && (
        <div className="guide-message">
          {message}
        </div>
      )}
    </div>
  );
}
