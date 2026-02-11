import React, { useContext, useEffect, useState, useMemo, useRef } from "react";
import { MemberContext } from "../../context/MemberContext";
import { ReviewContext } from "../../context/ReviewContext";
import { CommunityContext } from "../../context/CommunityContext";
import ProfileSidebar from "../../components/profile/ProfileSidebar";
import FoodMapSection from "../../components/profile/FoodMapSection";
import ReviewSection from "../../components/profile/ReviewSection";
import CommunitySection from "../../components/profile/CommunitySection";
import styles from "./Profile.module.css";

/**
 * Profile
 * 1) 본인 정보 노출 (왼쪽 사이드바)
 * 2) 본인이 선택한 item_ids만 "읽기 전용"으로 표시
 * 3) 내가 작성한 리뷰 목록
 * 4) 내가 작성한 커뮤니티 글 목록
 */
export default function Profile() {
  const { stateMember, memberActions } = useContext(MemberContext);
  const { stateReview, reviewActions } = useContext(ReviewContext);
  const { stateCommunity, communityActions } = useContext(CommunityContext);

  const [reviewPage, setReviewPage] = useState(0);
  const [communityPage, setCommunityPage] = useState(0);

  const me = stateMember.me;

  // ✅ 새로고침/직접 진입 등으로 me가 비어있을 때만 1회 보조 로드
  // (MemberProvider가 토큰 변화 시 자동으로 loadMe를 호출하므로, 여기서 매번 호출하면 중복될 수 있음)
  const requestedMeRef = useRef(false);

  // ✅ me가 없고 로딩 중도 아니면 1회만 loadMe 시도
  useEffect(() => {
    if (me) return;
    if (stateMember?.loading) return;
    if (requestedMeRef.current) return;
    requestedMeRef.current = true;
    memberActions?.loadMe?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [me, stateMember?.loading]);

  // ✅ 리뷰/커뮤니티는 인증(me) 준비된 뒤에 호출
  useEffect(() => {
    if (!me?.member_id) return;
    reviewActions.fetchMyList();
    communityActions.fetchMyList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [me?.member_id]);

  const myReviews = useMemo(() => stateReview.list ?? [], [stateReview.list]);

  const myCommunities = useMemo(() => {
    const list = stateCommunity.list ?? [];
    // fetchMyList가 이미 "내 글"만 내려주면 filter는 없어도 됨. (안전하게 유지)
    return list.filter((c) => c.member_id === me?.member_id);
  }, [stateCommunity.list, me?.member_id]);

  if (!me) {
    return (
      <div className={styles.loading}>
        <p>Loading...</p>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <div className={styles.grid}>
        <ProfileSidebar member={me} />

        <div>
          {stateMember?.error && <div className={styles.error}>{stateMember.error}</div>}

          <FoodMapSection communities={myCommunities} />

          <ReviewSection
            reviews={myReviews}
            currentPage={reviewPage}
            onPageChange={setReviewPage}
          />

          <CommunitySection
            communities={myCommunities}
            currentPage={communityPage}
            onPageChange={setCommunityPage}
          />
        </div>
      </div>
    </div>
  );
}
