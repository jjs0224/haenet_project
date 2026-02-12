import api from "./axiosInstance";

export const ReviewAPI = {
  //  영수증 검증
  verifyReceipt: (file) => {
    const fd = new FormData();
    fd.append("type", "receipt");
    fd.append("file", file);

    return api.post("/review/receipt/verify", fd, {
      headers: { "Content-Type": "multipart/form-data" },
    });
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

  // ---------------------------
  // Create Review from Receipt
  // POST /review/receipt/create
  // form-data:
  //  - receipt_id (job_id)
  //  - title, content, rating
  //  - menu_name (string)  (너 ReviewCreate에서 JSON.stringify(menuList)로 보내고 있음)
  //  - images (0~3) optional
  // ---------------------------
  async createFromReceipt({ receipt_id, title, content, rating, menu_name, images = [] }) {
    if (!receipt_id) throw new Error("receipt_id is required");
    if (!title) throw new Error("title is required");
    if (!content) throw new Error("content is required");

    const fd = new FormData();
    fd.append("receipt_id", receipt_id);
    fd.append("title", title);
    fd.append("content", content);
    fd.append("rating", String(rating ?? 5));

    // 너 프론트는 menu_name 필드로 보내고 있어서 그대로 유지
    if (menu_name != null) {
      fd.append("menu_name", String(menu_name));
    }

    const safeImgs = Array.isArray(images) ? images.slice(0, 3) : [];
    for (const f of safeImgs) {
      if (f) fd.append("images", f);
    }

    return axiosInstance.post("/review/receipt/create", fd);
  },

  //  전체 리뷰 리스트
  list: () => api.get("/review"),

  //  본인 리스트
  myList: () => api.get("/review/me"),

  //  리뷰 상세
  detail: (id) => api.get(`/review/${id}`),

  //  리뷰 내용만 수정
  updateContent: (id, review_content) =>
    api.patch(`/review/${id}`, { review_content }),
};
