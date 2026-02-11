import { useContext, useState, useEffect, useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";
import styles from "./ProfileSidebar.module.css";

import { MemberContext } from "../../context/MemberContext";
import { AuthContext } from "../../context/AuthContext";
import { MetaContext } from "../../context/MetaContext";
import { MemberAPI } from "../../api/memberApi";

/**
 * ProfileSidebar
 * 프로필 왼쪽 사이드바 컴포넌트
 */
export default function ProfileSidebar({ member }) {
  const nav = useNavigate();
  const { memberActions } = useContext(MemberContext);
  const { authActions } = useContext(AuthContext);
  const { stateMeta, metaActions } = useContext(MetaContext);

  const [withdrawing, setWithdrawing] = useState(false);

  // Load categories and items
  useEffect(() => {
    if (!stateMeta?.loading && (!stateMeta?.restrictions || stateMeta.restrictions.length === 0)) {
      metaActions?.refresh?.({ force: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Get selected item IDs from member
  const selectedIds = useMemo(() => (member?.item_ids ? member.item_ids : []), [member]);

  // Get restriction items that match selected IDs
  const restrictionItems = useMemo(() => {
    const categories = stateMeta?.restrictions || [];
    const items = [];

    categories.forEach(cat => {
      if (cat.items) {
        cat.items.forEach(item => {
          if (selectedIds.includes(item.item_id)) {
            items.push({
              id: item.item_id,
              label: item.item_label_en || item.item_label_ko || `Item #${item.item_id}`
            });
          }
        });
      }
    });

    return items;
  }, [stateMeta?.restrictions, selectedIds]);

  if (!member) {
    return (
      <div className={styles.loading}>
        <p>Loading...</p>
      </div>
    );
  }

  const onWithdraw = async () => {
    if (withdrawing) return;

    const ok = window.confirm(
      "Are you sure you want to leave the membership?\nData created may be deleted when you leave."
    );
    if (!ok) return;

    try {
      setWithdrawing(true);

      // 회원 탈퇴 요청
      await MemberAPI.withdraw();

      // 로그아웃(토큰/쿠키 정리)
      await authActions.logout();

      // 멤버 상태 초기화
      memberActions.clear?.();

      alert("Your membership withdrawal has been completed.");
      nav("/");
    } catch (e) {
      alert(e?.message || "회원 탈퇴 실패");
    } finally {
      setWithdrawing(false);
    }
  };

  return (
    <div className={styles.sidebar}>
      <div className={styles.profileSection}>
        <div className={styles.avatar}>
          {member.nickname?.charAt(0).toUpperCase() || "U"}
        </div>
        <h2 className={styles.nickname}>{member.nickname || "사용자"}</h2>
        <p className={styles.email}>{member.email}</p>
      </div>

      <div className={styles.infoSection}>
        <div className={styles.infoItem}>
          <p className={styles.infoLabel}>Country</p>
          <p className={styles.infoValue}>{member.country || "미설정"}</p>
        </div>
        <div className={styles.infoItem}>
          <p className={styles.infoLabel}>Gender</p>
          <p className={styles.infoValue}>{member.gender || "미설정"}</p>
        </div>
        <div className={styles.infoItem}>
          <p className={styles.infoLabel}>Dislike Ingredients</p>
          <div className={styles.dislikesList}>
            {member.dislike_tags && member.dislike_tags.length > 0 ? (
              member.dislike_tags.map((tag, index) => (
                <span key={index} className={styles.dislikeTag}>
                  {tag}
                </span>
              ))
            ) : (
              <p className={styles.infoValue}>None</p>
            )}
          </div>
        </div>

        {/* Restriction Items */}
        {restrictionItems.length > 0 && (
          <div className={styles.infoItem}>
            <p className={styles.infoLabel}>Dietary</p>
            <div className={styles.restrictionItemsList}>
              {restrictionItems.map((item) => (
                <span key={item.id} className={styles.restrictionItemTag}>
                  {item.label}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className={styles.actions}>
        <Link to="/member/edit" className={styles.editButton}>
          Information Edit
        </Link>

        {/* 회원 탈퇴 */}
        <button
          type="button"
          onClick={onWithdraw}
          disabled={withdrawing}
          style={{
            marginTop: 10,
            width: "100%",
            padding: "10px 12px",
            borderRadius: 7,
            border: "1px solid #ffb4b4",
            background: "#fff5f5",
            color: "#c00",
            cursor: withdrawing ? "not-allowed" : "pointer",
            fontWeight: 700,
          }}
        >
          {withdrawing ? "Processing withdrawal..." : "Membership Withdrawal"}
        </button>
      </div>
    </div>
  );
}
