import React, { createContext, useReducer } from "react";
import { CommunityAPI } from "../api/communityApi";

export const CommunityContext = createContext(null);

const initial = { list: [], detail: null, loading: false, error: "" };

function reducer(state, action) {
  switch (action.type) {
    case "LOADING":
      return { ...state, loading: true, error: "" };
    case "SET_LIST":
      return { ...state, list: action.payload || [], loading: false };
    case "SET_DETAIL":
      return { ...state, detail: action.payload, loading: false };
    case "ERROR":
      return { ...state, loading: false, error: action.payload || "error" };
    default:
      return state;
  }
}

export function CommunityProvider({ children }) {
  const [stateCommunity, dispatch] = useReducer(reducer, initial);

  const communityActions = {
    // 전체: active만
    fetchList: async () => {
      dispatch({ type: "LOADING" });
      try {
        const r = await CommunityAPI.list();
        const list = Array.isArray(r.data) ? r.data : r.data?.items ?? [];
        dispatch({ type: "SET_LIST", payload: list });
        return list;
      } catch (e) {
        dispatch({ type: "ERROR", payload: e.message });
        return [];
      }
    },

    // 내것: active 상관없이 전부
    fetchMyList: async () => {
      dispatch({ type: "LOADING" });
      try {
        const r = await CommunityAPI.myList();
        const list = Array.isArray(r.data) ? r.data : r.data?.items ?? [];
        dispatch({ type: "SET_LIST", payload: list });
        return list;
      } catch (e) {
        dispatch({ type: "ERROR", payload: e.message });
        return [];
      }
    },

    fetchDetail: async (id) => {
      dispatch({ type: "LOADING" });
      try {
        const r = await CommunityAPI.detail(id);
        dispatch({ type: "SET_DETAIL", payload: r.data });
        return r.data;
      } catch (e) {
        dispatch({ type: "ERROR", payload: e.message });
        return null;
      }
    },

    create: async (payload) => (await CommunityAPI.create(payload)).data,
    update: async (id, payload) => (await CommunityAPI.update(id, payload)).data,
//     remove: async (id) => (await CommunityAPI.remove(id)).data,

    // 0217 jk 추가
    jobStatus: async (jobId) => (await CommunityAPI.jobStatus(jobId)).data,


    /**
     * 추천 토글
     * - 여기서는 "토글 요청 + 응답 반환"만 수행
     * - 화면 반영은 CommunityList/Detail에서 fetchList/fetchDetail로 확정 갱신
     */
    recommendToggle: async (communityId) => {
      try {
        const r = await CommunityAPI.recommendToggle(communityId);
        return r.data; // { recommended: boolean, recommend: number } 기대
      } catch (e) {
        dispatch({ type: "ERROR", payload: e.message });
        throw e;
      }
    },
  };

  return (
    <CommunityContext.Provider value={{ stateCommunity, communityActions }}>
      {children}
    </CommunityContext.Provider>
  );
}
