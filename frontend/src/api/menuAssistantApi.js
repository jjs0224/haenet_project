import api from "./axiosInstance";

export const MenuAssistantAPI = {
  enqueue: ({ file, userProfile, runStep4 = true, runStep5 = true, runStep6 = true }) => {
    const fd = new FormData();
    fd.append("image", file);
    if (userProfile) {
      fd.append("user_profile_json", JSON.stringify(userProfile));
    }
    fd.append("run_step4", String(runStep4));
    fd.append("run_step5", String(runStep5));
    fd.append("run_step6", String(runStep6));

    return api.post("/menu/assistant", fd, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },
};
