import React, { useContext, useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { AuthContext } from "../context/AuthContext";
import CaptureFlow from "../components/camera/CaptureFlow";
import "./Home.css";

const LOGO_SRC = "/food_ray_logo.png";

/* ── SVG 아이콘 ── */
const CameraIcon = () => (
  <svg
    width="26"
    height="26"
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
  >
    <path
      d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <circle
      cx="12"
      cy="13"
      r="4"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

const ImageIcon = () => (
  <svg
    width="26"
    height="26"
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
  >
    <rect
      x="3"
      y="3"
      width="18"
      height="18"
      rx="2"
      ry="2"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <circle
      cx="8.5"
      cy="8.5"
      r="1.5"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <polyline
      points="21,15 16,10 5,21"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

const AnalyzeIcon = () => (
  <svg
    width="28"
    height="28"
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
  >
    <circle
      cx="11"
      cy="11"
      r="8"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <line
      x1="21"
      y1="21"
      x2="16.65"
      y2="16.65"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
    />
  </svg>
);

export default function Home() {
  const navigate = useNavigate();
  const { stateAuth } = useContext(AuthContext);

  const [mode, setMode] = useState("idle"); // "idle" | "camera"
  const [selectedImage, setSelectedImage] = useState(null);
  const [logoSrc, setLogoSrc] = useState(LOGO_SRC);

  const fileInputRef = useRef(null);
  const lastObjectUrlRef = useRef(null);

  // objectURL 정리
  useEffect(() => {
    return () => {
      if (lastObjectUrlRef.current) {
        URL.revokeObjectURL(lastObjectUrlRef.current);
        lastObjectUrlRef.current = null;
      }
    };
  }, []);

  const setPreviewFromFile = (file) => {
    setSelectedImage(file);

    if (lastObjectUrlRef.current) {
      URL.revokeObjectURL(lastObjectUrlRef.current);
      lastObjectUrlRef.current = null;
    }
    const url = URL.createObjectURL(file);
    lastObjectUrlRef.current = url;
    setLogoSrc(url);
  };

  const handleImageSelect = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // ✅ 업로드 선택 시 카메라가 덮고 있으면 먼저 내림
    setMode("idle");
    setPreviewFromFile(file);
  };

  const handleCameraClick = () => {
    if (!stateAuth.accessToken) {
      navigate("/login?msg=login_required");
      return;
    }
    // ✅ 카메라 눌렀으면 카메라가 보여야 함
    setMode("camera");
  };

  const handleFileSelectClick = () => {
    // ✅ 카메라 → 업로드 전환 시, 카메라 먼저 내리고 업로드 오픈
    setMode("idle");

    // 렌더 반영 후 파일 선택 열기
    requestAnimationFrame(() => {
      if (fileInputRef.current) {
        fileInputRef.current.removeAttribute("capture");
        fileInputRef.current.click();
      }
    });
  };

  const handleRemoveImage = () => {
    setSelectedImage(null);
    setLogoSrc(LOGO_SRC);

    if (lastObjectUrlRef.current) {
      URL.revokeObjectURL(lastObjectUrlRef.current);
      lastObjectUrlRef.current = null;
    }

    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleAnalyze = () => {
    if (!selectedImage) return;

    if (!stateAuth.accessToken) {
      navigate("/login?msg=login_required");
      return;
    }

    window.__menuFile = selectedImage;
    navigate("/result");
  };

  return (
    <div className="home-container">
      <div className="home-logo-wrap">
        {mode === "camera" ? (
          <CaptureFlow
            onDone={(file) => {
              // ✅ 촬영 완료 → 카메라 내리고 업로드 미리보기 노출
              setMode("idle");
              setPreviewFromFile(file);
            }}
            onCancel={() => setMode("idle")}
          />
        ) : (
          <>
            <img src={logoSrc} alt="로고" className="home-logo" />
            {selectedImage && (
              <button
                onClick={handleRemoveImage}
                className="home-remove-btn"
                aria-label="이미지 삭제"
              >
                ×
              </button>
            )}
          </>
        )}
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        onChange={handleImageSelect}
        style={{ display: "none" }}
      />

      <div className="home-bottom-area">
        {/* ✅ 버튼 UI는 그대로 유지 */}
        <div className="home-pick-bar">
          <button onClick={handleCameraClick} className="home-pick-btn">
            <CameraIcon />
            <span>Camera</span>
          </button>
          <div className="home-pick-divider" />
          <button onClick={handleFileSelectClick} className="home-pick-btn">
            <ImageIcon />
            <span>Upload Image</span>
          </button>
        </div>

        <button
          onClick={handleAnalyze}
          disabled={!selectedImage}
          className="home-analyze-btn"
        >
          <AnalyzeIcon />
          <span>Analyze Menu</span>
        </button>
      </div>
    </div>
  );
}