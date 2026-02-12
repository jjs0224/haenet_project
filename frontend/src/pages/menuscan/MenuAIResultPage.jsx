import { useEffect, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { MenuAPI } from "../../api/menuApi";
import MenuAIResultView from "./MenuAIResultView";
import './menuscan.css';

export default function MenuAIResultPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const file = location.state?.file;
  const [loading, setLoading] = useState(true);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  /* =========================
     Validate input + run AI
  ========================= */

  useEffect(() => {
    // const file = location.state?.file;

    if (!file) {
      console.warn(
        "MenuAIResultPage: file missing"
      );
      navigate("/", { replace: true });
      return;
    }

    let cancelled = false;

    const run = async () => {
      try {
        const response =
          await MenuAPI.uploadMenu(file);

        if (!cancelled) {
          setResult(
            response?.data ?? response
          );
          setLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err?.response?.data?.detail ||
              err?.message ||
              "Menu analysis failed"
          );
          setLoading(false);
        }
      }
    };

    run();

    return () => {
      cancelled = true;
    };
  }, [file, navigate]);

  /* =========================
     Render states
  ========================= */

  if (loading) {
    return (
      <div className="ai-loading-root">
        <div className="ai-loading-box">
          <div className="ai-spinner" />
          <p>Analyzing menu...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="ai-error-root">
        <p>{error}</p>
        <button
          onClick={() => navigate("/")}
        >
          Back to home
        </button>
      </div>
    );
  }

  return (
    <MenuAIResultView
      result={result}
      onRestart={() => navigate("/")}
    />
  );
}
