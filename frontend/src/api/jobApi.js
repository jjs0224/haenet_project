import api from "./axiosInstance";

export const JobAPI = {
  get: (jobId) => api.get(`/jobs/${jobId}`),
};
