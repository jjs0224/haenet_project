import React, { useEffect, useRef, useState } from "react";
import { CameraService } from "./CameraService";
import "./Camera.css";

const GUIDE_MESSAGE = {
  TOO_DARK: "Too dark. Move to a brighter spot.",
  BLURRY: "Blurred. Focus on the text.",
  SHAKING: "Keep your device steady.",
  LOW_RESOLUTION:
    "Low resolution camera detected. Please upload an image or use a mobile device."
};

const ERROR_MESSAGE = {
  PERMISSION_DENIED: "Camera access is required.",
  NO_CAMERA_DEVICE: "No camera found.",
  CAMERA_IN_USE: "Camera is being used by another app.",
  UNSUPPORTED_BROWSER: "Browser not supported.",
  UNKNOWN_CAMERA_ERROR: "Unable to start camera."
};

export default function CameraCapture({ onComplete }) {
  const videoRef = useRef(null);
  const cameraRef = useRef(null);
  const qualityTimerRef = useRef(null);

  const [started, setStarted] = useState(false);
  const [guide, setGuide] = useState(null);
  const [guideColor, setGuideColor] = useState("white");
  const [error, setError] = useState(null);
  const [capturing, setCapturing] = useState(false);

  /* ===== Camera Start ===== */
  const startCamera = async () => {
    try {
      if (!cameraRef.current) {
        cameraRef.current = new CameraService(videoRef.current);
      }
      await cameraRef.current.start();
      setStarted(true);
      startQualityLoop();
    } catch (e) {
      setError(ERROR_MESSAGE[e.code] || ERROR_MESSAGE.UNKNOWN_CAMERA_ERROR);
    }
  };

  /* ===== Quality Loop ===== */
  const startQualityLoop = () => {
    stopQualityLoop();
    qualityTimerRef.current = setInterval(() => {
      if (!cameraRef.current) return;

      const result = cameraRef.current.canCapture();
      const analysis = cameraRef.current.analyzeFrame();

      if (!result.ok) {
        setGuide(result.reason);
        setGuideColor("white");
        return;
      }

      if (!analysis.shaken && analysis.sharpness > 20) {
        setGuide(null);
        setGuideColor("green");
      } else {
        setGuide(null);
        setGuideColor("white");
      }
    }, 300);
  };

  const stopQualityLoop = () => {
    if (qualityTimerRef.current) {
      clearInterval(qualityTimerRef.current);
      qualityTimerRef.current = null;
    }
  };

  /* ===== Capture ===== */
  const handleCapture = async () => {
    if (!cameraRef.current || capturing) return;

    const result = cameraRef.current.canCapture();
    if (!result.ok) {
      setGuide(result.reason);
      return;
    }

    setCapturing(true);
    try {
      const file = await cameraRef.current.capture();
      onComplete(file);
    } finally {
      setCapturing(false);
      cleanup();
    }
  };

  const handleSwitchCamera = async () => {
    if (!cameraRef.current) return;
    await cameraRef.current.switchCamera();
  };

  const cleanup = () => {
    stopQualityLoop();
    cameraRef.current?.stop();
    cameraRef.current = null;
    setStarted(false);
  };

  useEffect(() => {
    startCamera();
    return cleanup;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="camera-view">
      <video ref={videoRef} autoPlay playsInline muted />

      <div className={`camera-overlay ${guideColor === "green" ? "good" : ""}`}>
        <div className="crosshair" />
        <div className="h-line" />
        <div className="v-line" />
      </div>

      {guide && (
        <div
          className={`camera-guide ${
            guide === "LOW_RESOLUTION" ? "low" : "warn"
          }`}
        >
          {GUIDE_MESSAGE[guide]}
        </div>
      )}

      {started && (
        <div className="camera-controls">
          <button onClick={handleSwitchCamera}>Switch</button>
          <button onClick={handleCapture} disabled={guide !== null}>
            Capture
          </button>
        </div>
      )}

      {error && <p className="error">{error}</p>}
    </div>
  );
}
