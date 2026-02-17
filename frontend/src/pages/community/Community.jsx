import { useState, useContext, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import styles from "../../styles/Community.module.css";
import CommunityList from "../../components/community/CommunityList";
import CreateModal from "../../components/community/CreateModal";
import { AuthContext } from "../../context/AuthContext";
import { CommunityContext } from "../../context/CommunityContext";
import { ReviewContext } from "../../context/ReviewContext";
import { safeLocal } from "../../utils/storage";

// ✅ 폴링용: axios instance (토큰 자동 포함)
import api from "../../api/axiosInstance";

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

  // ✅ 언마운트/이탈 시 setState 방지
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

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

  // ✅ community job DONE/FAILED까지 폴링
  const pollCommunityJobUntilDone = async (jobId) => {
    const intervalMs = 1500;   // 폴링 간격
    const timeoutMs = 120000;  // 2분 타임아웃(필요하면 늘려도 됨)
    const startedAt = Date.now();

    while (mountedRef.current) {
      // GET /community/job/{job_id}
      const res = await api.get(`/community/job/${jobId}`);
      const data = res?.data;

      const status = data?.status;

      if (status === "DONE") {
        return data?.result; // ✅ 여기 result가 기존 community create 결과(community_id, image_urls...) 형태
      }

      if (status === "FAILED") {
        const msg =
          data?.error?.message ||
          data?.error?.detail ||
          "AI 이미지 생성에 실패했습니다.";
        throw new Error(msg);
      }

      if (Date.now() - startedAt > timeoutMs) {
        throw new Error(
          "AI 이미지 생성이 지연되고 있습니다. 잠시 후 My Journal에서 다시 확인해주세요."
        );
      }

      await new Promise((r) => setTimeout(r, intervalMs));
    }

    // 언마운트로 루프가 끝난 경우
    throw new Error("요청이 취소되었습니다.");
  };

  const handleConfirm = async ({ templateId, reviewIds }) => {
    setError("");
    setSaving(true);

    try {
      // 1) enqueue 요청: { job_id, status: "PENDING" } 형태로 옴
      const enqueueRes = await communityActions.create({
        template_id: templateId,
        review_ids: reviewIds,
      });

      if (!mountedRef.current) return;

      // 2) DONE까지 폴링해서 "최종 결과"를 받는다
      let finalResult = enqueueRes;

      if (enqueueRes?.job_id) {
        finalResult = await pollCommunityJobUntilDone(enqueueRes.job_id);
      }

      if (!mountedRef.current) return;

      // 3) template2(map)면 foodmap local storage 업데이트 (기존 로직 유지)
      if (Number(templateId) === 2 && finalResult?.image_urls?.length > 0) {
        safeLocal.set("foodmap_image_url", finalResult.image_urls[0]);
        if (finalResult.community_id) {
          safeLocal.set("foodmap_community_id", String(finalResult.community_id));
        }
        window.dispatchEvent(new Event("foodmap-updated"));
      }

      // 4) UI 갱신
      setIsModalOpen(false);
      setOnlyMine(true);
      await communityActions.fetchMyList();
    } catch (e) {
      if (!mountedRef.current) return;
      setError(e?.message || "AI 이미지 생성에 실패했습니다.");
    } finally {
      if (!mountedRef.current) return;
      setSaving(false);
    }
  };

  return (
    <div className={styles.container}>
      <h1 className={styles.title}>Community</h1>

      {/* 버튼 영역 */}
      <div className={styles.buttonRow}>
        <button
          className={styles.button}
          onClick={() => {
            if (!stateAuth.accessToken) {
              nav("/login");
              return;
            }
            setIsModalOpen(true);
          }}
        >
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
          className={`${styles.filterBtn} ${
            !onlyMine ? styles.filterActive : ""
          }`}
          onClick={() => {
            setOnlyMine(false);
            setLoginGuide(false);
          }}
        >
          All
        </button>
        <button
          className={`${styles.filterBtn} ${
            onlyMine ? styles.filterActive : ""
          }`}
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
        onClose={() => {
          if (!saving) setIsModalOpen(false);
        }}
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


// import { useState, useContext, useEffect } from "react";
// import { useNavigate } from "react-router-dom";
// import styles from "../../styles/Community.module.css";
// import CommunityList from "../../components/community/CommunityList";
// import CreateModal from "../../components/community/CreateModal";
// import { AuthContext } from "../../context/AuthContext";
// import { CommunityContext } from "../../context/CommunityContext";
// import { ReviewContext } from "../../context/ReviewContext";
// import { safeLocal } from "../../utils/storage";
//
// export default function Community() {
//   const nav = useNavigate();
//   const { stateAuth } = useContext(AuthContext);
//   const { stateCommunity, communityActions } = useContext(CommunityContext);
//   const { stateReview, reviewActions } = useContext(ReviewContext);
//
//   const [onlyMine, setOnlyMine] = useState(false);
//   const [isModalOpen, setIsModalOpen] = useState(false);
//   const [saving, setSaving] = useState(false);
//   const [error, setError] = useState("");
//   const [loginGuide, setLoginGuide] = useState(false);
//
//   useEffect(() => {
//     if (onlyMine) {
//       communityActions.fetchMyList();
//     } else {
//       communityActions.fetchList();
//     }
//     // eslint-disable-next-line react-hooks/exhaustive-deps
//   }, [onlyMine]);
//
//   useEffect(() => {
//     communityActions.fetchList();
//     // eslint-disable-next-line react-hooks/exhaustive-deps
//   }, []);
//
//   const handleConfirm = async ({ templateId, reviewIds }) => {
//     setError("");
//     setSaving(true);
//     try {
//       const result = await communityActions.create({
//         template_id: templateId,
//         review_ids: reviewIds,
//       });
//
//       if (templateId === 2 && result?.image_urls?.length > 0) {
//         safeLocal.set("foodmap_image_url", result.image_urls[0]);
//         if (result.community_id) {
//           safeLocal.set("foodmap_community_id", String(result.community_id));
//         }
//         window.dispatchEvent(new Event("foodmap-updated"));
//       }
//
//       setIsModalOpen(false);
//       setOnlyMine(true);
//       await communityActions.fetchMyList();
//     } catch (e) {
//       setError(e.message || "AI 이미지 생성에 실패했습니다.");
//     } finally {
//       setSaving(false);
//     }
//   };
//
//   return (
//     <div className={styles.container}>
//       <h1 className={styles.title}>Community</h1>
//
//       {/* <ReviewProgressIcons count={activeCount} />
//
//         <button
//         type="button"
//         disabled={!canGenerate}
//         onClick={() => setIsOpen(true)}
//         >
//         AI Image
//         </button>
//
//         {!canGenerate && (
//         <p style={{ fontSize: 13, color: "#999", marginTop: 4 }}>
//             리뷰 3개를 작성하면 AI 이미지를 생성할 수 있어요
//         </p>
//         )} */}
//
//       {/* 버튼 영역 */}
//       <div className={styles.buttonRow}>
//         <button className={styles.button} onClick={() => {
//           if (!stateAuth.accessToken) { nav("/login"); return; }
//           setIsModalOpen(true);
//         }}>
//           AI Image
//         </button>
//         <button className={styles.button} onClick={() => nav("/review/new")}>
//           + New Review
//         </button>
//       </div>
//
//       {error && <div className={styles.errorMsg}>{error}</div>}
//
//       {/* 내 저널 필터 */}
//       <div className={styles.filterRow}>
//         <button
//           className={`${styles.filterBtn} ${!onlyMine ? styles.filterActive : ""}`}
//           onClick={() => { setOnlyMine(false); setLoginGuide(false); }}
//         >
//           All
//         </button>
//         <button
//           className={`${styles.filterBtn} ${onlyMine ? styles.filterActive : ""}`}
//           onClick={() => {
//             if (!stateAuth.accessToken) {
//               setLoginGuide(true);
//               return;
//             }
//             setLoginGuide(false);
//             setOnlyMine(true);
//           }}
//         >
//           My Journal
//         </button>
//       </div>
//
//       {/* AI Image 생성 모달 — saving 중이면 닫기 불가 */}
//       <CreateModal
//         isOpen={isModalOpen}
//         onClose={() => { if (!saving) setIsModalOpen(false); }}
//         stateReview={stateReview}
//         reviewActions={reviewActions}
//         onConfirm={handleConfirm}
//         saving={saving}
//       />
//
//       {loginGuide && (
//         <div className={styles.loginGuideBox}>Please Sign in</div>
//       )}
//
//       <CommunityList
//         list={[...stateCommunity.list].sort((a, b) => {
//           const da = new Date(a.updated_at || a.created_at || 0);
//           const db = new Date(b.updated_at || b.created_at || 0);
//           return db - da;
//         })}
//         loading={stateCommunity.loading}
//         error={stateCommunity.error}
//       />
//     </div>
//   );
// }
