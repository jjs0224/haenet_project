import api from "./axiosInstance";

export const MenuAPI = {
  /**
   * @param {File} file
   * @param {object|string|null} userProfile - object 또는 JSON 문자열(또는 null)
   */
  uploadMenu: (file, userProfile = null) => {
    const fd = new FormData();
    fd.append("type", "menu");
    fd.append("file", file);

    // ✅ user_profile 키는 "항상" 붙임(빈 값이어도 키가 생성됨)
    let profileText = "";
    if (userProfile) {
      if (typeof userProfile === "string") {
        profileText = userProfile;
      } else {
        profileText = JSON.stringify(userProfile);
      }
    }
    fd.append("user_profile", profileText);

    return api.post("/menu/upload", fd, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },
};
