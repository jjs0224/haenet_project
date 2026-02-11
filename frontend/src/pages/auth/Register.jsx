import "../../styles/Register.css";
import Modal from "../../components/common/Modal";
import { COUNTRY_OPTIONS, GENDER } from "../../contents/register";
import { useContext, useEffect, useMemo, useState, useRef } from "react";
import { useNavigate} from "react-router-dom";
import { MetaContext } from "../../context/MetaContext";
import { MemberAPI } from "../../api/memberApi";
import api from "../../api/axiosInstance";
import RestrictionsPicker from "../../components/restrictions/RestrictionsPicker";

/* 정규식 */
const REGEX = {
  email: /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/,
  password: /^.{8,20}$/,
};

function validate(formData) {
  const errors = {};
  const email = formData.email.trim();

  if (!email) errors.email = "Email is required.";
  else if (!REGEX.email.test(email)) errors.email = "Invalid email format.";

  if (!formData.password) {
    errors.password = "Password is required.";
  } else if (!REGEX.password.test(formData.password)) {
    errors.password = "Password must be 8~20 characters.";
  }

  if (formData.password !== formData.passwordConfirm) {
    errors.passwordConfirm = "Password does not match.";
  }

  return errors;
}

/**
 * Register
 * - MetaContext(active 캐시) 기반으로 카테고리/아이템 노출
 * - RestrictionsPicker 공통 컴포넌트 사용
 * - 선택 item_ids 포함하여 회원가입 payload 전송
 */
export default function Register() {
  const nav = useNavigate();
  const { stateMeta, metaActions } = useContext(MetaContext);

  //  active True 리스트만 (MetaContext가 active 캐시라고 가정 + 안전 필터는 Picker에서 onlyActive로 처리)
  const categories = useMemo(() => stateMeta?.restrictions || [], [stateMeta?.restrictions]);

  const [form, setForm] = useState({
    email: "",
    nickname: "",
    password: "",
    passwordConfirm: "",
    gender: "",
    country: "",
  });

  const [itemIds, setItemIds] = useState([]);
  const [dislikes, setDislikes] = useState([]);
  const [dislikeInput, setDislikeInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState("");
  const [errors, setErrors] = useState({});
  const [checkStatus, setCheckStatus] = useState({
    nickname: null,
  });

  // Refs for input fields
  const emailRef = useRef(null);
  const passwordRef = useRef(null);
  const passwordConfirmRef = useRef(null);
  const nicknameRef = useRef(null);
  const genderRef = useRef(null);
  const countryRef = useRef(null);

  // meta 비어있으면 1회 강제 refresh
  useEffect(() => {
    if (!stateMeta?.loading && (categories || []).length === 0) {
      metaActions?.refresh?.({ force: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onChange = (e) => {
    const { name, value } = e.target;
    setForm((p) => ({ ...p, [name]: value }));

    // 닉네임 입력시 중복 확인 상태 초기화
    if (name === "nickname") {
      setCheckStatus({ nickname: null });
    }

    // 실시간 유효성 검사 (password 관련만)
    if (name === "password" || name === "passwordConfirm") {
      setErrors((p) => {
        const newErrors = { ...p };
        delete newErrors.password;
        delete newErrors.passwordConfirm;
        return newErrors;
      });
    }
  };

  const toggleItem = (id) => {
    setItemIds((prev) => {
      const s = new Set(prev);
      if (s.has(id)) s.delete(id);
      else s.add(id);
      return Array.from(s);
    });
  };

  const addDislike = () => {
    const trimmed = dislikeInput.trim();
    if (!trimmed) return;
    if (dislikes.length >= 3) return;
    if (dislikes.includes(trimmed)) {
      setMsg("❌ Already added ingredient.");
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

  // 닉네임 중복 확인 - 직접 API 호출
  const checkNickname = async () => {
    const nickname = form.nickname.trim();
    if (!nickname) {
      setCheckStatus({ nickname: null });
      return;
    }

    try {
      setLoading(true);
      // 직접 axios로 API 호출
      const response = await api.get(`/member/nickname/check?nickname=${encodeURIComponent(nickname)}`);

      // available이 true면 사용 가능, false면 중복
      if (response?.data?.available === true) {
        setCheckStatus({ nickname: true });
      } else {
        setCheckStatus({ nickname: false });
      }
    } catch (err) {
      console.error("Nickname check error:", err);
      setMsg("❌ Failed to check nickname");
      setCheckStatus({ nickname: null });
    } finally {
      setLoading(false);
    }
  };

  // 회원가입 실행 함수
  const submitSignup = async () => {
    setMsg("");

    // 유효성 검사
    const validationErrors = validate(form);
    if (Object.keys(validationErrors).length > 0) {
      setErrors(validationErrors);
      setMsg("❌ Please check the input information.");

      // Focus on the first invalid field
      if (validationErrors.email && emailRef.current) {
        emailRef.current.focus();
      } else if (validationErrors.password && passwordRef.current) {
        passwordRef.current.focus();
      } else if (validationErrors.passwordConfirm && passwordConfirmRef.current) {
        passwordConfirmRef.current.focus();
      }

      return false;
    }

    // 닉네임 중복 확인 여부 체크
    if (checkStatus.nickname !== true) {
      setMsg("❌ Please check nickname duplication");
      if (nicknameRef.current) {
        nicknameRef.current.focus();
      }
      return false;
    }

    // gender 선택 여부 체크
    if (!form.gender) {
      setMsg("❌ Please select your gender.");
      if (genderRef.current) {
        genderRef.current.focus();
      }
      return false;
    }

    // country 선택 여부 체크
    if (!form.country) {
      setMsg("❌ Please select your country.");
      if (countryRef.current) {
        countryRef.current.focus();
      }
      return false;
    }

    setLoading(true);
    try {
      const payload = {
        email: form.email.trim(),
        password: form.password,
        nickname: form.nickname.trim(),
        gender: form.gender || null,
        country: form.country || null,
        item_ids: itemIds,
        dislike_tags: dislikes.length > 0 ? dislikes : null,
      };

      console.log("SEND PAYLOAD:", payload);

      await MemberAPI.register(payload);
      console.log("Sign up success");
      setMsg(" Sign up success");
      return true;
    } catch (err) {
      const detail =
        err?.response?.data?.detail ||
        err?.response?.data?.message ||
        err?.message ||
        "Failed to sign up";
      setMsg(`❌ ${detail}`);
      return false;
    } finally {
      setLoading(false);
    }
  };

  const onSubmit = async (e) => {
    e.preventDefault();
    const success = await submitSignup();
    if (success) {
      setTimeout(() => nav("/login"), 1000);
    }
  };

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [modalType, setModalType] = useState(null);

  const openModal = (type) => {
    setModalType(type);
    setIsModalOpen(true);
  };

  const handleConfirm = async () => {
    if (modalType === "cancel") {
      console.log("Cancel Complete");
      setIsModalOpen(false);
      nav("/");
      return;
    }

    // signup
    if (modalType === "signup") {
      setIsModalOpen(false);
      const success = await submitSignup();
      if (success) {
        setTimeout(() => nav("/login"), 1000);
      }
    }
  };

  return (
    <div className="RegisterPage">
      <div className="RegisterHeader">
        <h2>Sign Up</h2>
      </div>

      {msg && <div className={`RegisterMsg ${msg.startsWith("") ? "ok" : "err"}`}>{msg}</div>}

      <form className="card RegisterForm" onSubmit={onSubmit}>
        <div className="row">
          <label>E-mail</label>
          <input
            ref={emailRef}
            name="email"
            value={form.email}
            onChange={onChange}
            placeholder="email@example.com"
            autoComplete="email"
          />
          {errors.email && <div className="errorText">{errors.email}</div>}
        </div>

        <div className="row">
          <label>Password (8~20 characters)</label>
          <input
            ref={passwordRef}
            name="password"
            value={form.password}
            onChange={onChange}
            type="password"
            placeholder="Not more than 8 to 20 letters"
            autoComplete="new-password"
          />
          {errors.password && <div className="errorText">{errors.password}</div>}
        </div>

        <div className="row">
          <label>Password Confirm</label>
          <input
            ref={passwordConfirmRef}
            name="passwordConfirm"
            value={form.passwordConfirm}
            onChange={onChange}
            type="password"
            placeholder="Re-enter password"
            autoComplete="new-password"
          />
          {errors.passwordConfirm && <div className="errorText">{errors.passwordConfirm}</div>}
        </div>

        <div className="row">
          <label>Nickname</label>
          <div style={{ display: "flex", gap: 8 }}>
            <input
              ref={nicknameRef}
              name="nickname"
              value={form.nickname}
              onChange={onChange}
              placeholder="Upto 10 characters"
              style={{ flex: 1 }}
            />
            <button
              type="button"
              className="checkBtn"
              onClick={checkNickname}
              disabled={loading || !form.nickname.trim()}
            >
              Check
            </button>
          </div>
          {checkStatus.nickname === true && <div className="successText"> Available nickname</div>}
          {checkStatus.nickname === false && <div className="errorText">❌ Nickname already in use</div>}
        </div>

        <div className="row">
          <label>Gender</label>
          <select ref={genderRef} name="gender" value={form.gender} onChange={onChange}>
            <option value="" disabled>
              Select Gender
            </option>

            {GENDER.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          {msg.includes("gender") && !form.gender && <div className="errorText">Please select your gender.</div>}
        </div>

        <div className="row">
          <label>Country</label>
          <select ref={countryRef} name="country" value={form.country} onChange={onChange}>
            <option value="" disabled>
              Select Country
            </option>

            {COUNTRY_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          {msg.includes("country") && !form.country && <div className="errorText">Please select your country.</div>}
        </div>

        {stateMeta?.loading && <div className="infoBox">Category Loading...</div>}
        {stateMeta?.error && <div className="errorBox">{stateMeta.error}</div>}

        {!stateMeta?.loading && (categories || []).length === 0 && (
          <div className="infoBox">
            There are no active categories/items.
            <button
              type="button"
              className="miniBtn"
              onClick={() => metaActions?.refresh?.({ force: true })}
              style={{ marginLeft: 8 }}
            >
              Calling back
            </button>
          </div>
        )}

        {/*  공통 컴포넌트 사용 */}
        <RestrictionsPicker
          categories={categories}
          selectedIds={itemIds}
          onToggle={toggleItem}
          mode="select"
          onlyActive={true}
        />

        <div className="RegisterDivider" />

        <div className="RegisterSectionTitle">
          <h3>Dislike Ingredients (Up to 3)</h3>
          <div className="sub">Enter ingredients you don't eat or dislike</div>
        </div>

        <div className="dislikesSection">
          <div className="row">
            <label>Add Ingredient</label>
            <div style={{ display: "flex", gap: 8 }}>
              <input
                type="text"
                value={dislikeInput}
                onChange={(e) => setDislikeInput(e.target.value)}
                onKeyDown={handleDislikeKeyDown}
                placeholder="e.g ) coriander (press Enter or click Add)"
                maxLength={50}
                disabled={dislikes.length >= 3}
                style={{ flex: 1 }}
              />
              <button
                type="button"
                className="checkBtn"
                onClick={addDislike}
                disabled={!dislikeInput.trim() || dislikes.length >= 3}
              >
                Add
              </button>
            </div>
          </div>

          {dislikes.length > 0 && (
            <div className="dislikeTagsContainer">
              {dislikes.map((dislike, index) => (
                <div className="dislikeTag" key={index}>
                  <span>{dislike}</span>
                  <button
                    type="button"
                    className="dislikeRemoveBtn"
                    onClick={() => removeDislike(index)}
                    aria-label="Remove"
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          )}

          <div className="dislikeCounter">
            {dislikes.length} / 3 ingredients added
          </div>
        </div>

        <div className="RegisterActions">
          <button type="button" onClick={() => openModal("cancel")}>
              Cancel
            </button>

            <button
              type="button"
              disabled={loading}
              onClick={() => openModal("signup")}
            >
              {loading ? "Signing up..." : "Sign Up"}
            </button>

            <Modal
              isOpen={isModalOpen}
              onClose={() => setIsModalOpen(false)}
              onConfirm={handleConfirm}
              message={
                modalType === "cancel"
                  ? "Are you sure you want to cancel?"
                  : "Do you want to proceed with sign up?"
              }
            />
        </div>
      </form>
    </div>
  );
}