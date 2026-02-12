import api from "./axiosInstance";

export const RestrictionsAdminAPI = {
  //  항상 "배열"만 리턴하도록 정규화
  list: async ({ onlyActive = false } = {}) => {
    const res = await api.get("/restrictions", {
      params: { only_active: onlyActive ? 1 : 0 },
    });
    const payload = res.data;
    const list = Array.isArray(payload) ? payload : (payload?.data ?? []);
    return list;
  },

  batchCreate: (payload) => api.post("/admin/restrictions/batch", payload),
  updateCategory: (id, payload) => api.put(`/admin/restrictions/category/${id}`, payload),
  updateItem: (id, payload) => api.put(`/admin/restrictions/item/${id}`, payload),
  addItemToCategory: (categoryId, payload) => api.post(`/admin/restrictions/category/${categoryId}/item`, payload),
};
