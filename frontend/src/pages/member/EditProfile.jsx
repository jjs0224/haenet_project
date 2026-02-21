import { useContext, useEffect, useMemo, useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { MemberContext } from "../../context/MemberContext";
import { MetaContext } from "../../context/MetaContext";
import RestrictionsPicker from "../../components/restrictions/RestrictionsPicker";
import styles from "./EditProfile.module.css";

/**
 * EditProfile
 * - 닉네임 수정 및 제한 아이템(item_ids) 수정 페이지
 * - 저장 시 PATCH /member/me 호출
 */
export default function EditProfile() {
  const nav = useNavigate();
  const { stateMember, memberActions } = useContext(MemberContext);
  const { stateMeta, metaActions } = useContext(MetaContext);

  const me = stateMember.me;

  // ✅ 새로고침/직접 진입: me가 없으면 1회만 불러오기
  const requestedMeRef = useRef(false);
  const categories = useMemo(
    () => stateMeta?.restrictions || [],
    [stateMeta?.restrictions]
  );

  // Form state
  const [form, setForm] = useState({
    nickname: "",
    item_ids: [],
  });

  const [dislikes, setDislikes] = useState([]);
  const [dislikeInput, setDislikeInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");
  const [msgType, setMsgType] = useState(""); // "success" or "error"

  // me 데이터 로드 → form 초기화
  useEffect(() => {
    if (!me) return;
    setForm({
      nickname: me.nickname || "",
      item_ids: Array.isArray(me.item_ids) ? me.item_ids : [],
    });
    setDislikes(Array.isArray(me.dislike_tags) ? me.dislike_tags : []);
  }, [me]);

  // ✅ me가 없고 로딩도 아니면 1회만 loadMe
  useEffect(() => {
    if (me) return;
    if (stateMember?.loading) return;
    if (requestedMeRef.current) return;
    requestedMeRef.current = true;
    memberActions?.loadMe?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [me, stateMember?.loading]);

  // meta 데이터 로드
  useEffect(() => {
    if (!stateMeta?.loading && categories.length === 0) {
      metaActions?.refresh?.({ force: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 핸들러들
  const handleNicknameChange = (e) => {
    setForm((prev) => ({ ...prev, nickname: e.target.value }));
  };

  const handleToggleItem = (id) => {
    setForm((prev) => {
      const itemSet = new Set(prev.item_ids || []);
      if (itemSet.has(id)) itemSet.delete(id);
      else itemSet.add(id);
      return { ...prev, item_ids: Array.from(itemSet) };
    });
  };

  const addDislike = () => {
    const trimmed = dislikeInput.trim();
    if (!trimmed) return;

    if (dislikes.length >= 3) {
      setMsg("Up to 3 ingredients only");
      setMsgType("error");
      return;
    }
    if (dislikes.includes(trimmed)) {
      setMsg("Already exist");
      setMsgType("error");
      return;
    }
    setDislikes([...dislikes, trimmed]);
    setDislikeInput("");
    setMsg("");
  };

  const removeDislike = (index) => {
    setDislikes(dislikes.filter((_, i) => i !== index));
  };

  const handleDislikeKeyDown = (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      addDislike();
    }
  };

  const handleSave = async () => {
    setMsg("");
    setMsgType("");
    setSaving(true);

    try {
      const payload = {
        nickname: form.nickname?.trim() || null,
        item_ids: form.item_ids || [],
        dislike_tags: dislikes,
      };

      // ✅ updateMe 안에서 update + loadMe까지 처리 (중복 호출 방지)
      await memberActions.updateMe(payload);

      nav("/member/profile");
    } catch (error) {
      const errorMsg =
        error?.response?.data?.detail ||
        error?.message ||
        "저장에 실패했습니다";
      setMsg(errorMsg);
      setMsgType("error");
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    nav("/member/profile");
  };

  if (!me) {
    return <div className={styles.container}>Loading...</div>;
  }

  return (
    <div className={styles.container}>
      <h2 className={styles.title}>Profile Edit</h2>

      {msg && (
        <div
          className={`${styles.message} ${
            msgType === "success" ? styles.messageSuccess : styles.messageError
          }`}
        >
          {msg}
        </div>
      )}

      {/* Nickname */}
      <div className={styles.card}>
        <div className={styles.formGroup}>
          <div className={styles.inputWrapper}>
            <label className={styles.label}>Nickname</label>
            <input
              type="text"
              value={form.nickname}
              onChange={handleNicknameChange}
              className={styles.input}
              placeholder="Please enter your nickname"
            />
          </div>
        </div>
      </div>

      {/* Restricted */}
      <div className={styles.restrictedSection}>
        <div className={styles.sectionHeader}>
          <h3 className={styles.sectionTitle}>Restricted information</h3>
          <div className={styles.selectedCount}>
            Choice:
            <span className={styles.selectedCountNumber}>
              {form.item_ids.length}
            </span>
          </div>
        </div>

        {stateMeta?.loading && (
          <div className={styles.loading}>Category Loading...</div>
        )}
        {stateMeta?.error && (
          <div className={styles.errorBox}>{stateMeta.error}</div>
        )}

        <RestrictionsPicker
          categories={categories}
          selectedIds={form.item_ids}
          onToggle={handleToggleItem}
          mode="select"
          onlyActive={true}
        />
      </div>

      {/* Dislike */}
      <div className={styles.dislikeSection}>
        <div className={styles.registerSectionTitle}>
          <h3>Dislike Ingredients (Up to 3)</h3>
          <div className={styles.sub}>
            Enter ingredients you don't eat or dislike
          </div>
        </div>

        <div className={styles.dislikesSection}>
          <div className={styles.row}>
            <label className={styles.label}>Add Ingredient</label>

            {/* ✅ inline style 제거하고 CSS로 통일 */}
            <div className={styles.inputRow}>
              <input
                type="text"
                value={dislikeInput}
                onChange={(e) => setDislikeInput(e.target.value)}
                onKeyDown={handleDislikeKeyDown}
                placeholder="e.g ) coriander (press Enter or click Add)"
                maxLength={50}
                disabled={dislikes.length >= 3}
                className={`${styles.input} ${styles.dislikeInput}`}
              />
              <button
                type="button"
                className={styles.dislikeAddButton}
                onClick={addDislike}
                disabled={!dislikeInput.trim() || dislikes.length >= 3}
              >
                Add
              </button>
            </div>
          </div>

          {dislikes.length > 0 && (
            <div className={styles.dislikeTagsContainer}>
              {dislikes.map((dislike, index) => (
                <div className={styles.dislikeTag} key={index}>
                  <span>{dislike}</span>
                  <button
                    type="button"
                    className={styles.dislikeRemoveBtn}
                    onClick={() => removeDislike(index)}
                    aria-label="Remove"
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          )}

          <div className={styles.dislikeCounter}>
            {dislikes.length} / 3 ingredients added
          </div>
        </div>
      </div>

      {/* Buttons */}
      <div className={styles.buttonWrapper}>
        <button
          onClick={handleCancel}
          className={`${styles.button} ${styles.buttonSecondary}`}
          disabled={saving}
        >
          Cancel
        </button>
        <button
          onClick={handleSave}
          className={`${styles.button} ${styles.buttonPrimary}`}
          disabled={saving}
        >
          {saving ? "Saving..." : "Save"}
        </button>
      </div>
    </div>
  );
}

// import { useContext, useEffect, useMemo, useState, useRef } from "react";
// import { useNavigate } from "react-router-dom";
// import { MemberContext } from "../../context/MemberContext";
// import { MetaContext } from "../../context/MetaContext";
// import RestrictionsPicker from "../../components/restrictions/RestrictionsPicker";
// import styles from "./EditProfile.module.css";
//
// /**
//  * EditProfile
//  * - 닉네임 수정 및 제한 아이템(item_ids) 수정 페이지
//  * - 저장 시 PATCH /member/me 호출
//  */
// export default function EditProfile() {
//   const nav = useNavigate();
//   const { stateMember, memberActions } = useContext(MemberContext);
//   const { stateMeta, metaActions } = useContext(MetaContext);
//
//   const me = stateMember.me;
//
//   // ✅ 새로고침/직접 진입: me가 없으면 1회만 불러오기
//   const requestedMeRef = useRef(false);
//   const categories = useMemo(() => stateMeta?.restrictions || [], [stateMeta?.restrictions]);
//
//   // Form state
//   const [form, setForm] = useState({
//     nickname: "",
//     item_ids: [],
//   });
//
//   const [dislikes, setDislikes] = useState([]);
//   const [dislikeInput, setDislikeInput] = useState("");
//   const [saving, setSaving] = useState(false);
//   const [msg, setMsg] = useState("");
//   const [msgType, setMsgType] = useState(""); // "success" or "error"
//
//   // me 데이터 로드 → form 초기화
//   useEffect(() => {
//     if (!me) return;
//     setForm({
//       nickname: me.nickname || "",
//       item_ids: Array.isArray(me.item_ids) ? me.item_ids : [],
//     });
//     setDislikes(Array.isArray(me.dislike_tags) ? me.dislike_tags : []);
//   }, [me]);
//
//   // ✅ me가 없고 로딩도 아니면 1회만 loadMe
//   useEffect(() => {
//     if (me) return;
//     if (stateMember?.loading) return;
//     if (requestedMeRef.current) return;
//     requestedMeRef.current = true;
//     memberActions?.loadMe?.();
//     // eslint-disable-next-line react-hooks/exhaustive-deps
//   }, [me, stateMember?.loading]);
//
//   // meta 데이터 로드
//   useEffect(() => {
//     if (!stateMeta?.loading && categories.length === 0) {
//       metaActions?.refresh?.({ force: true });
//     }
//     // eslint-disable-next-line react-hooks/exhaustive-deps
//   }, []);
//
//   // 핸들러들
//   const handleNicknameChange = (e) => {
//     setForm((prev) => ({ ...prev, nickname: e.target.value }));
//   };
//
//   const handleToggleItem = (id) => {
//     setForm((prev) => {
//       const itemSet = new Set(prev.item_ids || []);
//       if (itemSet.has(id)) itemSet.delete(id);
//       else itemSet.add(id);
//       return { ...prev, item_ids: Array.from(itemSet) };
//     });
//   };
//
//   const addDislike = () => {
//     const trimmed = dislikeInput.trim();
//     if (!trimmed) return;
//     if (dislikes.length >= 3) {
//       setMsg("Upto 3 images only");
//       setMsgType("error");
//       return;
//     }
//     if (dislikes.includes(trimmed)) {
//       setMsg("Already exist");
//       setMsgType("error");
//       return;
//     }
//     setDislikes([...dislikes, trimmed]);
//     setDislikeInput("");
//     setMsg("");
//   };
//
//   const removeDislike = (index) => {
//     setDislikes(dislikes.filter((_, i) => i !== index));
//   };
//
//   const handleDislikeKeyDown = (e) => {
//     if (e.key === "Enter") {
//       e.preventDefault();
//       addDislike();
//     }
//   };
//
//   const handleSave = async () => {
//     setMsg("");
//     setMsgType("");
//     setSaving(true);
//
//     try {
//       const payload = {
//         nickname: form.nickname?.trim() || null,
//         item_ids: form.item_ids || [],
//         dislike_tags: dislikes,
//       };
//
//       // ✅ updateMe 안에서 update + loadMe까지 처리 (중복 호출 방지)
//       await memberActions.updateMe(payload);
//
//       nav("/member/profile");
//     } catch (error) {
//       const errorMsg =
//         error?.response?.data?.detail ||
//         error?.message ||
//         "저장에 실패했습니다";
//       setMsg(errorMsg);
//       setMsgType("error");
//     } finally {
//       setSaving(false);
//     }
//   };
//
//   const handleCancel = () => {
//     nav("/member/profile");
//   };
//
//   if (!me) {
//     return <div className={styles.container}>Loading...</div>;
//   }
//
//   return (
//     <div className={styles.container}>
//       <h2 className={styles.title}>Profile Edit</h2>
//
//       {msg && (
//         <div
//           className={`${styles.message} ${
//             msgType === "success"
//               ? styles.messageSuccess
//               : styles.messageError
//           }`}
//         >
//           {msg}
//         </div>
//       )}
//
//       {/* Nickname */}
//       <div className={styles.card}>
//         <div className={styles.formGroup}>
//           <div className={styles.inputWrapper}>
//             <label className={styles.label}>Nickname</label>
//             <input
//               type="text"
//               value={form.nickname}
//               onChange={handleNicknameChange}
//               className={styles.input}
//               placeholder="Please enter your nickname"
//             />
//           </div>
//         </div>
//       </div>
//
//       {/* Restricted */}
//       <div className={styles.restrictedSection}>
//         <div className={styles.sectionHeader}>
//           <h3 className={styles.sectionTitle}>Restricted information</h3>
//           <div className={styles.selectedCount}>
//             Choice:
//             <span className={styles.selectedCountNumber}>
//               {form.item_ids.length}
//             </span>
//           </div>
//         </div>
//
//         {stateMeta?.loading && (
//           <div className={styles.loading}>Category Loading...</div>
//         )}
//         {stateMeta?.error && (
//           <div className={styles.errorBox}>{stateMeta.error}</div>
//         )}
//
//         <RestrictionsPicker
//           categories={categories}
//           selectedIds={form.item_ids}
//           onToggle={handleToggleItem}
//           mode="select"
//           onlyActive={true}
//         />
//       </div>
//
//       {/* Dislike */}
//       <div className={styles.dislikeSection}>
//         <div className={styles.registerSectionTitle}>
//           <h3>Dislike Ingredients (Up to 3)</h3>
//           <div className={styles.sub}>Enter ingredients you don't eat or dislike</div>
//         </div>
//
//         <div className={styles.dislikesSection}>
//           <div className={styles.row}>
//             <label className={styles.label}>Add Ingredient</label>
//             <div style={{ display: "flex", gap: 8 }}>
//               <input
//                 type="text"
//                 value={dislikeInput}
//                 onChange={(e) => setDislikeInput(e.target.value)}
//                 onKeyDown={handleDislikeKeyDown}
//                 placeholder="e.g ) coriander (press Enter or click Add)"
//                 maxLength={50}
//                 disabled={dislikes.length >= 3}
//                 className={styles.dislikeTextInput}
//               />
//               <button
//                 type="button"
//                 className={styles.checkBtn}
//                 onClick={addDislike}
//                 disabled={!dislikeInput.trim() || dislikes.length >= 3}
//               >
//                 Add
//               </button>
//             </div>
//           </div>
//
//           {dislikes.length > 0 && (
//             <div className={styles.dislikeTagsContainer}>
//               {dislikes.map((dislike, index) => (
//                 <div className={styles.dislikeTag} key={index}>
//                   <span>{dislike}</span>
//                   <button
//                     type="button"
//                     className={styles.dislikeRemoveBtn}
//                     onClick={() => removeDislike(index)}
//                     aria-label="Remove"
//                   >
//                     ×
//                   </button>
//                 </div>
//               ))}
//             </div>
//           )}
//
//           <div className={styles.dislikeCounter}>
//             {dislikes.length} / 3 ingredients added
//           </div>
//         </div>
//       </div>
//
//       {/* Buttons */}
//       <div className={styles.buttonWrapper}>
//         <button
//           onClick={handleCancel}
//           className={`${styles.button} ${styles.buttonSecondary}`}
//           disabled={saving}
//         >
//           Cancel
//         </button>
//         <button
//           onClick={handleSave}
//           className={`${styles.button} ${styles.buttonPrimary}`}
//           disabled={saving}
//         >
//           {saving ? "Saving..." : "Save"}
//         </button>
//       </div>
//     </div>
//   );
// }
