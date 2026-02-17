import api from "./axiosInstance";

export const CommunityAPI = {
  // 전체: active만
  list: () => api.get("/community"),

  // 내것: active 상관없이
  myList: () => api.get("/community/me"),

  detail: (id) => api.get(`/community/${id}`),
  create: (payload) => api.post("/community", payload),
  update: (id, payload) => api.put(`/community/${id}`, payload),

  // 삭제 (Context에서 사용 중)
//  remove: (id) => api.delete(`/community/${id}`),

  // ---------------------------------
  // 댓글 (추후 백엔드 API 연결)
  // 예상: GET /community/{id}/comments?limit=10&offset=0
  //      POST /community/{id}/comments { content }
  // ---------------------------------
  comments: (id, params) => api.get(`/community/${id}/comments`, { params }),
  createComment: (id, payload) => api.post(`/community/${id}/comments`, payload),
  updateComment: (communityId, commentId, payload) =>
  api.put(`/community/${communityId}/comments/${commentId}`, payload),

  recommendToggle: (community_id) =>
  api.post(`/community/${community_id}/recommend`),

  toggleActive: (community_id) =>
  api.patch(`/community/${community_id}/active`),

  jobStatus: (jobId) => api.get(`/community/job/${jobId}`),
};
