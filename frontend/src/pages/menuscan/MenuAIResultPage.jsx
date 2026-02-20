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
        const response = await MenuAPI.uploadMenu(file);
        if (cancelled) return;

        const jobId = response?.data?.job_id;
        const status = response?.data?.status;

        if (!jobId) {
          throw new Error("서버에서 job_id를 받지 못했습니다.");
        }

        if (status === "DONE" && response?.data?.result) {
          setResult(response?.data ?? response);
          return;
        }

        const jobRes = await MenuAPI.waitMenuJob(jobId);
        if (cancelled) return;

        if (jobRes?.data?.status === "DONE") {
          setResult({ job_id: jobId, result: jobRes?.data?.result });
        } else {
          const err = jobRes?.data?.error;
          const errMsg = err?.message || err?.detail || JSON.stringify(err || {});
          setError(`분석 실패: ${errMsg}`);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err?.response?.data?.detail ||
              err?.message ||
              "Menu analysis failed"
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
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
