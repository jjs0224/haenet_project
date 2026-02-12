import React, { createContext, useEffect, useReducer, useMemo, useRef } from "react";
import { AuthAPI } from "../api/authApi";
import { setAccessToken } from "../api/axiosInstance";
import { safeSession } from "../utils/storage";

export const AuthContext = createContext(null);

const SS_KEY = "access_token";

const initial = {
  accessToken: safeSession.get(SS_KEY) || null,
  loading: true,
  error: "",
};

function reducer(state, action) {
  switch (action.type) {
    case "SET_TOKEN":
      return { ...state, accessToken: action.payload || null, error: "" };
    case "SET_LOADING":
      return { ...state, loading: !!action.payload };
    case "SET_ERROR":
      return { ...state, error: action.payload || "" };
    case "RESET":
      return { ...state, accessToken: null, loading: false, error: "" };
    default:
      return state;
  }
}

export function AuthProvider({ children }) {
  const [stateAuth, dispatch] = useReducer(reducer, initial);
  const didBootRef = useRef(false);

  const authActions = useMemo(() => {
    return {
      bootstrap: async () => {
        // StrictMode/재마운트 대비 1회만 실행
        if (didBootRef.current) return;
        didBootRef.current = true;

        dispatch({ type: "SET_LOADING", payload: true });
        dispatch({ type: "SET_ERROR", payload: "" });

        // 1) 세션 토큰 우선 적용
        const ssToken = safeSession.get(SS_KEY) || null;
        setAccessToken(ssToken);
        dispatch({ type: "SET_TOKEN", payload: ssToken });

        // 2) 자동로그인: 세션 토큰이 없으면 refresh 쿠키로 재발급 시도(1회)
        if (!ssToken) {
          try {
            const r = await AuthAPI.refresh(); // 401이면 null 리턴하도록 authApi에서 처리
            const token = r?.data?.access_token || null;

            if (token) {
              setAccessToken(token);
              safeSession.set(SS_KEY, token);
              dispatch({ type: "SET_TOKEN", payload: token });
            }
          } catch (e) {
            // 여기까지 오면 401 이외의 진짜 에러
            dispatch({ type: "SET_ERROR", payload: e?.message || "bootstrap failed" });
          }
        }

        dispatch({ type: "SET_LOADING", payload: false });
      },

      login: async (email, password) => {
        dispatch({ type: "SET_ERROR", payload: "" });

        const r = await AuthAPI.login(email, password);
        const token = r?.data?.access_token || null;

        if (!token) {
          dispatch({ type: "SET_ERROR", payload: "No access_token from login response" });
          return false;
        }

        setAccessToken(token);
        safeSession.set(SS_KEY, token);
        dispatch({ type: "SET_TOKEN", payload: token });

        window.dispatchEvent(new Event("auth-changed"));
        return true;
      },

      logout: async () => {
        dispatch({ type: "SET_ERROR", payload: "" });

        try {
          await AuthAPI.logout();
        } catch (e) {
          // ignore
        } finally {
          setAccessToken(null);
          safeSession.remove(SS_KEY);
          dispatch({ type: "RESET" });
          window.dispatchEvent(new Event("auth-changed"));
        }
      },
    };
  }, []);

  useEffect(() => {
    authActions.bootstrap();
  }, [authActions]);

  // 탭 동기화(선택)
  useEffect(() => {
    const sync = () => {
      const token = safeSession.get(SS_KEY) || null;
      setAccessToken(token);
      dispatch({ type: "SET_TOKEN", payload: token });
    };
    window.addEventListener("auth-changed", sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener("auth-changed", sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  return (
    <AuthContext.Provider value={{ stateAuth, authActions }}>
      {children}
    </AuthContext.Provider>
  );
}
