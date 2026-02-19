import React, { useContext } from "react";
import { useNavigate } from "react-router-dom";
import { AuthContext } from "../../context/AuthContext";
import { MemberContext } from "../../context/MemberContext";
import styles from "./CommunityList.module.css";

export default function CommunityList({ list = [], loading = false, error = "" }) {
  const nav = useNavigate();
  const { stateAuth } = useContext(AuthContext);
  const { stateMember } = useContext(MemberContext);
  const myMemberId = stateMember?.me?.member_id;
  const myNickname = stateMember?.me?.nickname;

  const handleCardClick = (e, id) => {
    if (!stateAuth.accessToken) {
      e.preventDefault();
      nav("/login");
      return;
    }
    nav(`/community/${id}`);
  };

  if (error) return <div className={styles.errorBox}>{error}</div>;
  if (loading) return <div className={styles.loading}>Loading...</div>;
  if (list.length === 0) return <div className={styles.empty}>커뮤니티 글이 없습니다.</div>;

  return (
    <div className={styles.listContainer}>
      <ul className={styles.list}>
        {list.map((row) => {
          const id = row.community_id ?? row.id;
          const imgUrl = row.image_urls?.[0] || null;
          const nickname = row.nickname || row.author_nickname || row.member_nickname
            || (row.member_id === myMemberId && myNickname ? myNickname : `익명`);

          return (
            <li key={id} className={styles.listItem}>
              <div onClick={(e) => handleCardClick(e, id)} className={styles.cardLink} style={{ cursor: "pointer" }}>
                {/* 상단 헤더: 프로필 아이콘 + 닉네임 */}
                <div className={styles.cardHeader}>
                  <div className={styles.headerLeft}>
                    <div className={styles.avatar}>{nickname.charAt(0).toUpperCase()}</div>
                    <div className={styles.cardNickname}>{nickname}</div>
                  </div>
                </div>

                {/* 이미지 영역 */}
                <div className={row.community_type === "map" ? styles.cardImageMap : styles.cardImage}>
                  {imgUrl ? (
                    <img src={imgUrl} alt={`community-${id}`} className={row.community_type === "map" ? styles.imgMap : styles.img} />
                  ) : (
                    <div className={styles.imgPlaceholder}>No image</div>
                  )}
                </div>

                {/* 좋아요 + 액션 */}
                <div className={styles.cardActions}>
                  <span className={styles.likeIcon}>♥</span>
                  <span className={styles.likeCount}>Like {row.recommend ?? 0}</span>
                </div>

                {/* 댓글 작성자 닉네임 + 최신 댓글 */}
                <div className={styles.cardComment}>
                  {row.latest_comment_text ? (
                    <>
                      <span className={styles.commentNickname}>
                        {row.latest_comment_nickname || "익명"}
                      </span>
                      <span className={styles.commentText}>{row.latest_comment_text}</span>
                    </>
                  ) : (
                    <span className={styles.commentText}>No comments</span>
                  )}
                </div>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}