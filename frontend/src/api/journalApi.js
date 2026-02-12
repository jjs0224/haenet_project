import api from "./axiosInstance";

export const JournalAPI = {
  enqueue: (payload) => api.post("/journal/generate", payload),
};
