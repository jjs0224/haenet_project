import api from "./axiosInstance";

export const MenuAssistantAPI = {
  enqueue: ({ file, userProfile, runStep4 = true, runStep5 = true, runStep6 = true }) => {
    const fd = new FormData();
    fd.append("type", "menu");
    fd.append("file", file);
    let profileText = "";
    if (userProfile) {
      profileText = typeof userProfile === "string" ? userProfile : JSON.stringify(userProfile);
    }
    fd.append("user_profile", profileText);

    return api.post("/menu/upload", fd, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },
};
