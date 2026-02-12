import axios from "axios";
import { safeSession } from "../utils/storage";

// ✅ 개발환경(CRA proxy 사용): baseURL을 "/"로 두면 package.json의 proxy를 탄다.
// ✅ 배포/특정 환경: REACT_APP_API_BASE_URL이 있으면 기존처럼 그 값을 그대로 사용
// ✅ 안전가드: http(s) 또는 / 로 시작하지 않으면 "/"로 강제
const RAW_BASE_URL = process.env.REACT_APP_API_BASE_URL;
const isValidBaseUrl =
    typeof RAW_BASE_URL === "string" &&
    (RAW_BASE_URL.startsWith("/") || /^https?:\/\//i.test(RAW_BASE_URL));
const BASE_URL = isValidBaseUrl ? RAW_BASE_URL : "/";

const api = axios.create({
    baseURL: BASE_URL,
    withCredentials: true,
});

const raw = axios.create({
    baseURL: BASE_URL,
    withCredentials: true,
});

// sessionStorage (safe wrapper for blocked storage contexts)
const SS_KEY = "access_token";
export const getAccessToken = () => safeSession.get(SS_KEY);

let accessToken = getAccessToken();
export const setAccessToken = (token) => {
    accessToken = token || null;
    if (token) safeSession.set(SS_KEY, token);
    else safeSession.remove(SS_KEY);
};

// refresh 싱글플라이트
let refreshPromise = null;
async function refreshAccessTokenOnce() {
    if (!refreshPromise) {
        refreshPromise = raw
            .post("/auth/refresh")
            .then((r) => {
                const newAccess = r.data?.access_token || null;
                setAccessToken(newAccess);
                return newAccess;
            })
            .catch((e) => {
                // refresh 401이면 그냥 null
                if (e?.response?.status === 401) return null;
                throw e;
            })
            .finally(() => {
                refreshPromise = null;
            });
    }
    return refreshPromise;
}

// request :: accToken을 여기서 담아주는 곳
api.interceptors.request.use((config) => {
    //  [추가] Content-Type 안전 처리 (FormData 업로드 보호)
    // - 영수증/이미지 업로드는 FormData라서 boundary 포함 Content-Type을 axios가 자동 설정해야 함
    // - 혹시 어디선가 Content-Type이 잘못 박히는 상황을 방지하기 위해 FormData면 제거
    // - JSON 요청은 Content-Type이 없을 때만 application/json 설정(선택)
    const isFormData =
        typeof FormData !== "undefined" && config.data instanceof FormData;

    config.headers = config.headers || {};

    if (isFormData) {
        delete config.headers["Content-Type"];
        delete config.headers["content-type"];
    } else {
        const method = (config.method || "get").toLowerCase();
        const hasBody =
            config.data !== undefined &&
            config.data !== null &&
            ["post", "put", "patch"].includes(method);

        if (hasBody) {
            if (!config.headers["Content-Type"] && !config.headers["content-type"]) {
                config.headers["Content-Type"] = "application/json";
            }
        }
    }

    if (accessToken) {
        config.headers.Authorization = `Bearer ${accessToken}`;
    }
    return config;
});

api.interceptors.response.use(
    (res) => res,
    async (error) => {
        const original = error.config;
        const status = error.response?.status;
        const url = original?.url || "";

        const isRefresh = url.includes("/auth/refresh");
        const isLogin = url.includes("/auth/login");
        const isLogout = url.includes("/auth/logout");

        // 핵심 변경:
        // refresh/login에서 401이 나도 sessionStorage 토큰을 지우지 않는다.
        // (logout만 토큰 정리)
        if (isRefresh || isLogin) {
            return Promise.reject(error);
        }
        if (isLogout) {
            setAccessToken(null);
            window.dispatchEvent(new Event("auth-changed"));
            return Promise.reject(error);
        }

        // 일반 API가 401일 때만 refresh 시도
        if (status === 401 && original && !original._retry) {
            original._retry = true;
            try {
                const newAccess = await refreshAccessTokenOnce();
                if (!newAccess)
                    throw new Error("No access token after refresh");

                original.headers = original.headers || {};
                original.headers.Authorization = `Bearer ${newAccess}`;

                window.dispatchEvent(new Event("auth-changed"));
                return api(original);
            } catch (e) {
                // 여기서만 accessToken 제거 (진짜 인증 깨짐)
                setAccessToken(null);
                window.dispatchEvent(new Event("auth-changed"));
                return Promise.reject(e);
            }
        }

        const msg =
            error.response?.data?.detail || error.message || "Request failed";
        return Promise.reject(new Error(msg));
    },
);

export default api;
