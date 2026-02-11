import React, { useContext, useEffect } from "react";
import { Link } from "react-router-dom";
import { CommunityContext } from "../../context/CommunityContext";
import "../../styles/Community.css";

function formatDate(v) {
  if (!v) return "-";
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return String(v);
  return d.toLocaleString();
}

export default function CommunityList() {
  const { stateCommunity, communityActions } = useContext(CommunityContext);
  const [loginGuide, setLoginGuide] = useState(false); // "로그인을 해주세요" 안내 표시 플래그

  useEffect(() => {
    communityActions.fetchList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (stateCommunity.error) return <div className="errorBox">{stateCommunity.error}</div>;
  if (stateCommunity.loading) return <div>Loading...</div>;

  if (!stateCommunity.list || stateCommunity.list.length === 0) {
    return <div className="notice">No community posts.</div>;
  }

  const onClickRecommend = async (e, id) => {
    e.preventDefault(); // 카드 Link 이동 방지
    e.stopPropagation();

    try {
      const out = await communityActions.recommendToggle(id);

      // 토글 후 리스트 재조회 -> 화면 반영 100%
      await communityActions.fetchList();
    } catch (err) {
      alert(err?.response?.data?.detail || err?.message || "Failed to recommend");
    }
  };

  return (
    <div className="communityCardList">
      {stateCommunity.list.map((row) => {
        const id = row.id ?? row.community_id;
        const img = row.image_urls?.[0] ?? row.imageUrl ?? row.image_url ?? "";
        const nickname = row.nickname ?? "-";
        const createdAt = formatDate(row.created_at ?? row.createdAt);
        const latestComment =
          row.latest_comment?.content ??
          row.latest_comment_text ??
          row.latest_comment ??
          null;

        // recommend 출력
        const recommend = row.recommend ?? 0;

        return (
          <Link key={id} to={`/community/${id}`} className="communityCard">
            <div className="communityCardThumb">
              {img ? (
                <img src={img} alt="community" />
              ) : (
                <div className="communityCardThumbPlaceholder">NO IMAGE</div>
              )}
            </div>

            <div className="communityCardBody">
              <div className="communityCardMeta">
                <div className="communityCardNickname">{nickname}</div>
                <div className="communityCardDate">{createdAt}</div>
              </div>

              <div className="communityCardComment">
                <span className="communityCardCommentLabel">Comments</span>
                <span className="communityCardCommentText">
                  {latestComment ? latestComment : "There isn't."}
                </span>
              </div>

              <div style={{ marginTop: 10, display: "flex", justifyContent: "flex-end" }}>
                <button
                  type="button"
                  onClick={(e) => onClickRecommend(e, id)}
                  style={{
                    padding: "6px 10px",
                    borderRadius: 10,
                    border: "1px solid #ddd",
                    background: "#fff",
                    cursor: "pointer",
                    fontSize: 14,          //  강제
                    color: "#111",         //  강제
                    lineHeight: "18px",    //  강제
                    minWidth: 60,          //  강제
                    textIndent: 0,         //  강제
                    overflow: "visible",   //  강제
                    whiteSpace: "nowrap",  //  강제
                  }}
                >
                  👍 {recommend}
                </button>
              </div>
            </div>
          </Link>
        );
      })}
    </div>
  );
}
