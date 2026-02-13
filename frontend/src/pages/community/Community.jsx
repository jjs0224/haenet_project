import { useState, useContext, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import styles from "../../styles/Community.module.css";
import CommunityList from "../../components/community/CommunityList";
import CreateModal from "../../components/community/CreateModal";
import { AuthContext } from "../../context/AuthContext";
import { CommunityContext } from "../../context/CommunityContext";
import { ReviewContext } from "../../context/ReviewContext";
// import ReviewProgress from "../../components/review/ReviewProgress";

export default function Community() {
  const nav = useNavigate();
  const { stateAuth } = useContext(AuthContext);
  const { stateCommunity, communityActions } = useContext(CommunityContext);
  const { stateReview, reviewActions } = useContext(ReviewContext);

  const [onlyMine, setOnlyMine] = useState(false);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [loginGuide, setLoginGuide] = useState(false);

  useEffect(() => {
    if (onlyMine) {
      communityActions.fetchMyList();
    } else {
      communityActions.fetchList();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onlyMine]);

  useEffect(() => {
    communityActions.fetchList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleConfirm = async ({ templateId, reviewIds }) => {
    setError("");
    setSaving(true);
    try {
      const result = await communityActions.create({
        template_id: templateId,
        review_ids: reviewIds,
      });

      if (templateId === 2 && result?.image_urls?.length > 0) {
        localStorage.setItem("foodmap_image_url", result.image_urls[0]);
        if (result.community_id) {
          localStorage.setItem("foodmap_community_id", String(result.community_id));
        }
        window.dispatchEvent(new Event("foodmap-updated"));
      }

      setIsModalOpen(false);
      setOnlyMine(true);
      await communityActions.fetchMyList();
    } catch (e) {
      setError(e.message || "AI 이미지 생성에 실패했습니다.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className={styles.container}>
      <h1 className={styles.title}>Community</h1>

      {/* <ReviewProgressIcons count={activeCount} />

        <button
        type="button"
        disabled={!canGenerate}
        onClick={() => setIsOpen(true)}
        >
        AI Image
        </button>

        {!canGenerate && (
        <p style={{ fontSize: 13, color: "#999", marginTop: 4 }}>
            리뷰 3개를 작성하면 AI 이미지를 생성할 수 있어요
        </p>
        )} */}

      {/* 버튼 영역 */}
      <div className={styles.buttonRow}>
        <button className={styles.button} onClick={() => {
          if (!stateAuth.accessToken) { nav("/login"); return; }
          setIsModalOpen(true);
        }}>
          AI Image
        </button>
        <button className={styles.button} onClick={() => nav("/review/new")}>
          + New Review
        </button>
      </div>

      {error && <div className={styles.errorMsg}>{error}</div>}

      {/* 내 저널 필터 */}
      <div className={styles.filterRow}>
        <button
          className={`${styles.filterBtn} ${!onlyMine ? styles.filterActive : ""}`}
          onClick={() => { setOnlyMine(false); setLoginGuide(false); }}
        >
          All
        </button>
        <button
          className={`${styles.filterBtn} ${onlyMine ? styles.filterActive : ""}`}
          onClick={() => {
            if (!stateAuth.accessToken) {
              setLoginGuide(true);
              return;
            }
            setLoginGuide(false);
            setOnlyMine(true);
          }}
        >
          My Journal
        </button>
      </div>

      {/* AI Image 생성 모달 — saving 중이면 닫기 불가 */}
      <CreateModal
        isOpen={isModalOpen}
        onClose={() => { if (!saving) setIsModalOpen(false); }}
        stateReview={stateReview}
        reviewActions={reviewActions}
        onConfirm={handleConfirm}
        saving={saving}
      />

      {loginGuide && (
        <div className={styles.loginGuideBox}>Please Sign in</div>
      )}

      <CommunityList
        list={[...stateCommunity.list].sort((a, b) => {
          const da = new Date(a.updated_at || a.created_at || 0);
          const db = new Date(b.updated_at || b.created_at || 0);
          return db - da;
        })}
        loading={stateCommunity.loading}
        error={stateCommunity.error}
      />
    </div>
  );
}