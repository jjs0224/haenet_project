import React, { useContext, useState } from "react";
import { useNavigate } from "react-router-dom";
import { CommunityContext } from "../../context/CommunityContext";
import CreateModal from "../../components/community/CreateModal";
import { ReviewContext } from "../../context/ReviewContext";

export default function CommunityCreate() {
  const nav = useNavigate();
  const { communityActions } = useContext(CommunityContext);
  const { stateReview, reviewActions } = useContext(ReviewContext);

  const [isOpen, setIsOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  const handleConfirm = async ({ templateId, reviewIds }) => {
    setSaving(true);
    const payload = {
      template_id: templateId,
      review_ids: reviewIds,
    }


    try {
      await communityActions.create(payload);
      // console.log("[CommunityCreate] create response:", created);


      setIsOpen(false);     // 모달 닫기
      nav("/community");    // 커뮤니티 목록으로 이동
    } catch (e) {
      alert(e.message || "Generate AI image failed");
    } finally {
      setSaving(false);
    }
  };

  
  return (
    <div style={{ padding: 16, maxWidth: 720 }}>
      <h2>New Community Post</h2>

      <button type="button" onClick={() => setIsOpen(true)} disabled={saving}>
        리뷰선택
      </button>

      <CreateModal
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        stateReview={stateReview}
        reviewActions={reviewActions}
        onConfirm={handleConfirm}   // 이름 맞추기
        saving={saving}            // (선택) 버튼 disable용
      />

    </div>
  );
}