import React, { useContext, useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { AuthContext } from "../context/AuthContext";
import CaptureFlow from "../components/camera/CaptureFlow";
import "./Home.css";

const LOGO_SRC = "/food_ray_logo.png";

/* ── SVG 아이콘 ── */
const CameraIcon = () => (
  <svg width="26" height="26" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path
      d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
    />
    <circle
      cx="12" cy="13" r="4"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
    />
  </svg>
);

const ImageIcon = () => (
  <svg width="26" height="26" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
    <rect
      x="3" y="3" width="18" height="18" rx="2" ry="2"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
    />
    <circle
      cx="8.5" cy="8.5" r="1.5"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
    />
    <polyline
      points="21,15 16,10 5,21"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
    />
  </svg>
);

const AnalyzeIcon = () => (
  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
    <circle
      cx="11" cy="11" r="8"
      stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"
    />
    <line
      x1="21" y1="21" x2="16.65" y2="16.65"
      stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"
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

  const handleImageSelect = (e) => {
    const file = e.target.files?.[0];
    if (file) {
      setSelectedImage(file);
      setLogoSrc(URL.createObjectURL(file));
    }
  };

  const handleCameraClick = () => {
    if (!stateAuth.accessToken) {
      navigate("/login?msg=login_required");
      return;
    }
    setMode("camera");
  };

  const handleFileSelectClick = () => {
    if (fileInputRef.current) {
      fileInputRef.current.removeAttribute("capture");
      fileInputRef.current.click();
    }
  };

  const handleRemoveImage = () => {
    setSelectedImage(null);
    setLogoSrc(LOGO_SRC);
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
      {/* 로고 영역 (화면의 ~75%) */}
      <div className="home-logo-wrap">
        {mode === "camera" ? (
          <CaptureFlow
            onDone={(file) => {
              setSelectedImage(file);
              setLogoSrc(URL.createObjectURL(file));
              setMode("idle");
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

      {/* 숨겨진 파일 입력 */}
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        onChange={handleImageSelect}
        style={{ display: "none" }}
      />

      {/* 하단 영역 (~25%): 카메라·파일 바 + 분석 버튼 */}
      <div className="home-bottom-area">
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


// import React, { useContext, useState, useRef } from "react";
// import { useNavigate } from "react-router-dom";
// import { AuthContext } from "../context/AuthContext";
// import CaptureFlow from "../components/camera/CaptureFlow";
// import "./Home.css";
//
// const LOGO_SRC = "/food_ray_logo.png";
//
// /* ── SVG 아이콘 ── */
// const CameraIcon = () => (
//   <svg width="26" height="26" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
//     <path
//       d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"
//       stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
//     />
//     <circle
//       cx="12" cy="13" r="4"
//       stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
//     />
//   </svg>
// );
//
// const ImageIcon = () => (
//   <svg width="26" height="26" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
//     <rect
//       x="3" y="3" width="18" height="18" rx="2" ry="2"
//       stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
//     />
//     <circle
//       cx="8.5" cy="8.5" r="1.5"
//       stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
//     />
//     <polyline
//       points="21,15 16,10 5,21"
//       stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
//     />
//   </svg>
// );
//
// const AnalyzeIcon = () => (
//   <svg width="28" height="28" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
//     <circle
//       cx="11" cy="11" r="8"
//       stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"
//     />
//     <line
//       x1="21" y1="21" x2="16.65" y2="16.65"
//       stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"
//     />
//   </svg>
// );
//
// export default function Home() {
//   const navigate = useNavigate();
//   const { stateAuth } = useContext(AuthContext);
//
//   // ✅ added (needed for camera flow)
//   const [mode, setMode] = useState("idle"); // "idle" | "camera"
//
//   const [selectedImage, setSelectedImage] = useState(null);
//   const [logoSrc, setLogoSrc] = useState(LOGO_SRC);
//   const fileInputRef = useRef(null);
//
//   const handleImageSelect = (e) => {
//     const file = e.target.files?.[0];
//     if (file) {
//       setSelectedImage(file);
//       setLogoSrc(URL.createObjectURL(file));
//     }
//   };
//
//   // ✅ camera button now opens CaptureFlow (instead of input capture attribute trick)
//   const handleCameraClick = () => {
//     if (!stateAuth.accessToken) {
//       navigate("/login?msg=login_required");
//       return;
//     }
//     setMode("camera");
//   };
//
//   const handleFileSelectClick = () => {
//     if (fileInputRef.current) {
//       fileInputRef.current.removeAttribute("capture");
//       fileInputRef.current.click();
//     }
//   };
//
//   const handleRemoveImage = () => {
//     setSelectedImage(null);
//     setLogoSrc(LOGO_SRC);
//     if (fileInputRef.current) fileInputRef.current.value = "";
//   };
//
//   // ✅ keep EXACTLY like base code: use window.__menuFile then go /result
//   const handleAnalyze = () => {
//     if (!selectedImage) return;
//
//     if (!stateAuth.accessToken) {
//       navigate("/login?msg=login_required");
//       return;
//     }
//
//     window.__menuFile = selectedImage;
//     navigate("/result");
//   };
//
//   return (
//     <div className="home-container">
//       {/* 로고 영역 (화면의 ~75%) */}
//       <div className="home-logo-wrap">
//         {mode === "camera" ? (
//           <CaptureFlow
//             onDone={(file) => {
//               setSelectedImage(file);
//               setLogoSrc(URL.createObjectURL(file));
//               setMode("idle");
//             }}
//             onCancel={() => setMode("idle")}
//           />
//         ) : (
//           <>
//             <img src={logoSrc} alt="로고" className="home-logo" />
//             {selectedImage && (
//               <button
//                 onClick={handleRemoveImage}
//                 className="home-remove-btn"
//                 aria-label="이미지 삭제"
//               >
//                 ×
//               </button>
//             )}
//           </>
//         )}
//       </div>
//
//       {/* 숨겨진 파일 입력 */}
//       <input
//         ref={fileInputRef}
//         type="file"
//         accept="image/*"
//         onChange={handleImageSelect}
//         style={{ display: "none" }}
//       />
//
//       {/* 하단 영역 (~25%): 카메라·파일 바 + 분석 버튼 */}
//       <div className="home-bottom-area">
//         <div className="home-pick-bar">
//           <button onClick={handleCameraClick} className="home-pick-btn">
//             <CameraIcon />
//             <span>Camera</span>
//           </button>
//           <div className="home-pick-divider" />
//           <button onClick={handleFileSelectClick} className="home-pick-btn">
//             <ImageIcon />
//             <span>Upload Image</span>
//           </button>
//         </div>
//
//         <button
//           onClick={handleAnalyze}
//           disabled={!selectedImage}
//           className="home-analyze-btn"
//         >
//           <AnalyzeIcon />
//           <span>Analyze Menu</span>
//         </button>
//       </div>
//     </div>
//   );
// }
