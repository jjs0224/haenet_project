import { useState, useEffect, useContext } from "react";
import { MemberContext } from "../../context/MemberContext";
import styles from "./Section.module.css";
import mapStyles from "./FoodMapSection.module.css";

/**
 * FoodMapSection
 * template2(map)로 생성된 '먹거리 지도' 이미지를 표시
 * communities prop에서 현재 로그인한 member_id와 일치하는 map 타입 커뮤니티의 이미지를 표시
 */
export default function FoodMapSection({ communities = [] }) {
  const [imageUrl, setImageUrl] = useState(null);
  const { stateMember } = useContext(MemberContext);
  const currentMemberId = stateMember?.me?.member_id;

  // 현재 로그인한 사용자의 map 타입 커뮤니티 찾기
  useEffect(() => {
    if (!currentMemberId || !communities.length) {
      setImageUrl(null);
      return;
    }

    // 현재 사용자가 작성한 map 타입 커뮤니티 찾기
    const mapCommunity = communities.find(
      (c) => c.member_id === currentMemberId && c.community_type === "map"
    );

    if (mapCommunity?.image_urls?.[0]) {
      setImageUrl(mapCommunity.image_urls[0]);
    } else {
      setImageUrl(null);
    }
  }, [communities, currentMemberId]);

  if (!imageUrl) return null;

  return (
    <div className={styles.section}>
      <div className={styles.header}>
        <h3 className={styles.title}>Food map</h3>
      </div>
      <div className={mapStyles.mapImageWrap}>
        <img
          src={imageUrl}
          alt="Food Map"
          className={mapStyles.mapImage}
        />
      </div>
    </div>
  );
}
