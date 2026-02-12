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

  //  리뷰 생성(영수증 receipt_id 기반)
  createFromReceipt: ({ receipt_id, title, content, rating, location, menu_name, images }) => {
    const fd = new FormData();
    fd.append("receipt_id", receipt_id);
    fd.append("title", title);
    fd.append("content", content);
    fd.append("rating", String(rating));
  
    if (location) fd.append("location", location);
    if (menu_name) fd.append("menu_name", menu_name);

    (images || []).forEach((img) => fd.append("images", img));

    return api.post("/review/create", fd, {
      headers: { "Content-Type": "multipart/form-data" },
    });
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
