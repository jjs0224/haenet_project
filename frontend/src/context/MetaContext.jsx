import React, { createContext, useEffect, useMemo, useReducer } from "react";
import { MetaAPI } from "../api/metaApi";
import { safeLocal } from "../utils/storage";

export const MetaContext = createContext(null);

const initial = {
  restrictions: [],
  loading: false,
  loaded: false,
  error: null,
};

function reducer(state, action) {
  switch (action.type) {
    case "LOAD_START":
      return { ...state, loading: true, error: null };
    case "LOAD_OK":
      return { ...state, loading: false, loaded: true, restrictions: action.payload || [] };
    case "LOAD_ERR":
      return { ...state, loading: false, error: action.error || "error" };
    case "RESET":
      return initial;
    default:
      return state;
  }
}

export function MetaProvider({ children }) {
  const [stateMeta, dispatch] = useReducer(reducer, initial);

  const metaActions = useMemo(() => {
    const loadRestrictions = async ({ force = false } = {}) => {
      if (!force && stateMeta.loaded) return;
      dispatch({ type: "LOAD_START" });
      try {
        const res = await MetaAPI.getActiveRestrictions();
        const list = Array.isArray(res?.data?.data) ? res.data.data : (res?.data || []);

        dispatch({ type: "LOAD_OK", payload: list });

        // ✅ localStorage 캐시 (ReviewDetail에서 읽을 수 있게)
        try {
          safeLocal.set("meta_categories", JSON.stringify(list));
        } catch {}
      } catch (e) {
        dispatch({ type: "LOAD_ERR", error: e?.response?.data?.detail || e?.message });
      }
    };

    return {
      loadRestrictions,
      refresh: loadRestrictions, // refresh는 loadRestrictions의 별칭
      reset: () => dispatch({ type: "RESET" }),
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stateMeta.loaded]);

  // ✅ 앱 시작 시 1번 로드 (어느 페이지로 들어가도 meta 준비되게)
  useEffect(() => {
    metaActions.loadRestrictions({ force: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const value = useMemo(() => ({ stateMeta, metaActions }), [stateMeta, metaActions]);
  return <MetaContext.Provider value={value}>{children}</MetaContext.Provider>;
}
