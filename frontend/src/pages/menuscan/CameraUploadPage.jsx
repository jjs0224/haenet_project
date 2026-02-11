import React, { useEffect, useRef, useState } from 'react';
import PreviewPage from './PreviewPage';
import { CameraService } from '../../components/camera/CameraService';

const GUIDE_MESSAGE = {
  READY: 'Center the menu in the frame.',
  TOO_DARK: 'Too dark. Move to a brighter spot.',
  BLURRY: 'Blurred. Focus on the text.',
  SHAKING: 'Keep your device steady.',
  LOW_RESOLUTION:
    'Low resolution camera detected. Please upload an image or use a mobile device.'
};

const ERROR_MESSAGE = {
  PERMISSION_DENIED: 'Camera access is required.',
  NO_CAMERA_DEVICE: 'No camera found.',
  CAMERA_IN_USE: 'Camera is being used by another app.',
  UNSUPPORTED_BROWSER: 'Browser not supported.',
  UNKNOWN_CAMERA_ERROR: 'Unable to start camera.'
};

export default function CameraUploadPage({ onCapture }) {
  const videoRef = useRef(null);
  const cameraRef = useRef(null);
  const qualityTimerRef = useRef(null);

  const [started, setStarted] = useState(false);
  const [error, setError] = useState(null);
  const [guide, setGuide] = useState(null);

  const [capturedImage, setCapturedImage] = useState(null);
  const [capturing, setCapturing] = useState(false);
  const [previewStep, setPreviewStep] = useState(false);
  const [cameraClosed, setCameraClosed] = useState(false);

  /* =========================
     Camera Start (user gesture)
     ========================= */

  const startCamera = async () => {
    setError(null);
    setCameraClosed(false);

    try {
      if (!cameraRef.current) {
        cameraRef.current = new CameraService(videoRef.current);
      }

      await cameraRef.current.start();
      setStarted(true);
      startQualityLoop();
    } catch (e) {
      setError(
        ERROR_MESSAGE[e.code] || ERROR_MESSAGE.UNKNOWN_CAMERA_ERROR
      );
    }
  };

  /* =========================
     Quality Check Loop
     ========================= */

  const startQualityLoop = () => {
    stopQualityLoop();

    qualityTimerRef.current = setInterval(() => {
      if (!cameraRef.current) return;

      const result = cameraRef.current.canCapture();
      if (!result.ok) {
        setGuide(result.reason);
      } else {
        setGuide(null);
      }
    }, 300);
  };

  const stopQualityLoop = () => {
    if (qualityTimerRef.current) {
      clearInterval(qualityTimerRef.current);
      qualityTimerRef.current = null;
    }
  };

  /* =========================
     Capture
     ========================= */

  const handleCapture = async () => {
    if (!cameraRef.current) return;

    const result = cameraRef.current.canCapture();
    if (!result.ok) {
      setGuide(result.reason);
      return;
    }

    if (capturing) return;
    setCapturing(true);

    try {
      const imageFile = await cameraRef.current.capture();
      stopCameraSafely(true);
      setCapturedImage(imageFile);
      setPreviewStep(true);
    } finally {
      setCapturing(false);
    }
  };


  /* =========================
     Switch Camera
     ========================= */

  const handleSwitchCamera = async () => {
    if (!cameraRef.current) return;

    try {
      await cameraRef.current.switchCamera();
    } catch (e) {
      setError(
        ERROR_MESSAGE[e.code] || ERROR_MESSAGE.UNKNOWN_CAMERA_ERROR
      );
    }
  };

  /* =========================
     File Input Fallback
     ========================= */

  const handleFileChange = e => {
    const file = e.target.files && e.target.files[0];
    if (!file) return;

    stopCameraSafely(false);
    setCapturedImage(file);
    setPreviewStep(true);
  };

  /* =========================
     Cleanup helpers
     ========================= */

  const stopCameraSafely = showClosedMessage => {
    stopQualityLoop();

    if (cameraRef.current) {
      cameraRef.current.stop();
      cameraRef.current = null;
    }

    setStarted(false);
    setGuide(null);

    if (showClosedMessage) {
      setCameraClosed(true);
    }
  };

  /* =========================
     Mount / Unmount
     ========================= */

  useEffect(() => {
    return () => {
      stopCameraSafely(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* =========================
     Preview
     ========================= */

  if (previewStep) {
    return (
      <PreviewPage
        file={capturedImage}
        goBack={() => {
          setCapturedImage(null);
          setPreviewStep(false);
          setStarted(false);
          setGuide(null);
          setCameraClosed(false);
        }}
      />
    );
  }

  /* =========================
     Render
     ========================= */

  return (
    <div className="camera-upload-page">
      <h2>Menu Scan</h2>

      <div className="camera-view">
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
        />
      </div>

      {!started && (
        <>
          <p>Please allow camera access to take photos.</p>

          <button onClick={startCamera}>
            Start Camera
          </button>

          <p>Or, upload an image.</p>

          <input
            type="file"
            accept="image/*"
            capture="environment"
            onChange={handleFileChange}
          />

          {cameraClosed && (
            <p className="info">
              Camera closed successfully.
            </p>
          )}

          {error === ERROR_MESSAGE.NO_CAMERA_DEVICE && (
            <p className="info">
              No camera detected. Please upload an image instead.
            </p>
          )}

          {error && error !== ERROR_MESSAGE.NO_CAMERA_DEVICE && (
            <p className="error">{error}</p>
          )}
        </>
      )}

      {started && (
        <>
          {guide && (
            <div className="camera-guide">
              {GUIDE_MESSAGE[guide]}
            </div>
          )}

          <div className="camera-controls">
            <button onClick={handleSwitchCamera}>
              Switch Camera
            </button>

            <button
              onClick={handleCapture}
              disabled={guide !== null}
            >
              Capture
            </button>
          </div>
        </>
      )}
    </div>
  );
}