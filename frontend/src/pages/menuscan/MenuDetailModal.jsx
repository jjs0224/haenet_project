import "./MenuDetailModal.css";

function safeArr(v) {
  return Array.isArray(v) ? v : [];
}

export default function MenuDetailModal({ item, onClose }) {
  if (!item) return null;

  // ✅ final_translated 기준 + 하위호환
  const menuNameEn = item?.menu_name_en || item?.menu?.menu_name_en || "";
  const menuNameKo = item?.menu_name_ko || item?.menu?.menu_name_ko || "";
  const menuDescEn =
    item?.menu_description_en || item?.menu?.menu_description_en || "";
  const riskDescEn =
    item?.risk_description_en || item?.risk?.risk_description_en || "";

  // const riskDifficulty = item?.risk_difficulty ?? item?.risk?.risk_difficulty ?? null;

  const commentKo = item?.comment_ko || item?.comment?.comment_ko || "";
  const commentEn = item?.comment_en || item?.comment?.comment_en || "";
  const hasComment = Boolean(commentKo || commentEn);

  // ✅ NEW: user_risk_match 표시
  const urm = item?.user_risk_match || {};
  const allergyHits = safeArr(urm?.allergy_tag_hits);
  const avoidHits = safeArr(urm?.avoid_food_hits);
  const religionHits = safeArr(urm?.religion_hits);
  // const hasAnyRisk = Boolean(urm?.has_any_risk);

  // alg_ 접두사 제거 함수
  const removeAlgPrefix = (label) => {
    if (typeof label !== 'string') return label;
    return label.replace(/^alg_/i, '');
  };

  return (
    <div className="ms-mdm__overlay" onClick={onClose}>
      <div className="ms-mdm__modal" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="ms-mdm__header">
          <div className="ms-mdm__titleWrap">
            <div className="ms-mdm__subtitle">Menu details (EN)</div>
            <h3 className="ms-mdm__title">
              {menuNameEn || menuNameKo || "Menu details"}
              {menuNameEn || menuNameKo || "Menu details"}
            </h3>
            {menuNameKo && menuNameEn && (
              <div className="ms-mdm__subline">{menuNameKo}</div>
            )}
          </div>

          <button className="ms-mdm__close" onClick={onClose}>
            Close
          </button>
        </div>

        {/* ✅ User risk match (NEW) */}
        <section className="ms-mdm__section">
          <h4 className="ms-mdm__sectionTitle">User risk match</h4>
          <div className="ms-mdm__riskBox">
            {allergyHits.length > 0 && (
              <div style={{ marginBottom: 8 }}>
                <div style={{ fontWeight: 700, marginBottom: 4 }}>
                  Allergy Tags
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                  {allergyHits.map((t) => (
                    <span key={t} className="ms-mdm__chip">
                      {removeAlgPrefix(t)}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {avoidHits.length > 0 && (
              <div style={{ marginBottom: 8 }}>
                <div style={{ fontWeight: 700, marginBottom: 4 }}>
                  Foods to Avoid
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                  {avoidHits.map((t) => (
                    <span key={t} className="ms-mdm__chip">
                      {removeAlgPrefix(t)}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {religionHits.length > 0 && (
              <div>
                <div style={{ fontWeight: 700, marginBottom: 4 }}>
                  Religious Restrictions
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                  {religionHits.map((t) => (
                    <span key={t} className="ms-mdm__chip">
                      {removeAlgPrefix(t)}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {allergyHits.length === 0 &&
              avoidHits.length === 0 &&
              religionHits.length === 0 && (
                <div style={{ opacity: 0.8 }}>
                  No matched risks from user profile.
                </div>
              )}
          </div>
        </section>

        {/* English description */}
        {menuDescEn && (
          <section className="ms-mdm__section">
            <h4 className="ms-mdm__sectionTitle">Food description</h4>
            <p className="ms-mdm__text">{menuDescEn}</p>
          </section>
        )}

        {/* Risk */}
        {riskDescEn && (
          <section className="ms-mdm__section">
            <h4 className="ms-mdm__sectionTitle">
              Allergy / dietary risk (EN)
            </h4>
            <div className="ms-mdm__riskBox">
              <p className="ms-mdm__riskText">{riskDescEn}</p>
            </div>
          </section>
        )}

        {/* Comment for staff */}
        {hasComment && (
          <section className="ms-mdm__section">
            <div className="ms-mdm__commentHeader">
              <h4 className="ms-mdm__sectionTitle">Show this to staff</h4>
            </div>

            <div className="ms-mdm__commentBox">
              {commentKo && (
                <div className="ms-mdm__commentBlock">
                  <div className="ms-mdm__langLabel">Korean (KO)</div>
                  <div className="ms-mdm__commentKo">{commentKo}</div>
                </div>
              )}

              {commentKo && commentEn && <div className="ms-mdm__divider" />}

              {commentEn && (
                <div className="ms-mdm__commentBlock">
                  <div className="ms-mdm__langLabel">English (EN)</div>
                  <div className="ms-mdm__commentEn">{commentEn}</div>
                </div>
              )}
            </div>
            
          </section>
        )}
      </div>
    </div>
  );
}
