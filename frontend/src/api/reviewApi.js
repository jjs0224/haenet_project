import api from "./axiosInstance";

export const ReviewAPI = {
  //  영수증 검증
  verifyReceipt: (file) => {
    const fd = new FormData();
    fd.append("type", "receipt");
    fd.append("file", file);

    // ✅ Content-Type 직접 지정하지 말기(axios가 boundary 포함 자동 설정)
    return api.post("/review/receipt/verify", fd);
  },

  getReceiptJob: (jobId) => api.get(`/review/receipt/job/${jobId}`),

  waitReceiptJob: async (jobId, opts = {}) => {
    const intervalMs = opts.intervalMs ?? 2000;
    const maxAttempts = opts.maxAttempts ?? 90;
    for (let i = 0; i < maxAttempts; i += 1) {
      const res = await ReviewAPI.getReceiptJob(jobId);
      const status = res?.data?.status;
      if (status === "DONE" || status === "FAILED") return res;
      await new Promise((r) => setTimeout(r, intervalMs));
    }
    throw new Error("review receipt job timeout");
  },

  // Create Review from Receipt
  async createFromReceipt({
    receipt_id,
    title,
    content,
    rating,
    menu_name,
    images = [],
  }) {
    if (!receipt_id) throw new Error("receipt_id is required");
    if (!title) throw new Error("title is required");
    if (!content) throw new Error("content is required");

    const fd = new FormData();
    fd.append("receipt_id", receipt_id);
    fd.append("title", title);
    fd.append("content", content);
    fd.append("rating", String(rating ?? 5));

    if (menu_name != null) {
      fd.append("menu_name", String(menu_name));
    }

    const safeImgs = Array.isArray(images) ? images.slice(0, 3) : [];
    for (const f of safeImgs) {
      if (f) fd.append("images", f);
    }

    // ✅ 여기 한 줄이 빌드 깨던 원인 (axiosInstance -> api)
    return api.post("/review/create", fd);
  },

  //  전체 리뷰 리스트
  list: () => api.get("/review"),

  //  본인 리스트
  myList: () => api.get("/review/me"),

  //  리뷰 상세
  detail: (id) => api.get(`/review/${id}`),

  //  리뷰 내용만 수정
  updateContent: (id, review_content) => api.patch(`/review/${id}`, { review_content }),
};
