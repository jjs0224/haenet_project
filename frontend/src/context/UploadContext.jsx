import React, { createContext, useReducer } from "react";
import { MenuAPI } from "../api/menuApi";

export const UploadContext = createContext(null);

const initial = {
  lastResult: null,
  uploading: false,
  error: "",
};

function reducer(state, action) {
  switch (action.type) {
    case "UPLOADING":
      return { ...state, uploading: true, error: "" };
    case "DONE":
      return { ...state, uploading: false, lastResult: action.payload, error: "" };
    case "ERROR":
      return { ...state, uploading: false, error: action.payload || "error" };
    default:
      return state;
  }
}

export function UploadProvider({ children }) {
  const [stateUpload, dispatch] = useReducer(reducer, initial);

  const uploadActions = {
    upload: async ({ file, type }) => {
      dispatch({ type: "UPLOADING" });
      try {
        const fd = new FormData();
        fd.append("file", file);
        fd.append("type", type); // menu / receipt

        const r = await MenuAPI.upload(fd);
        // console.log("실제 넘어가는 값 :: ", r.data)

        dispatch({ type: "DONE", payload: r.data });
        return r.data;
      } catch (e) {
        dispatch({ type: "ERROR", payload: e.message });
        throw e;
      }
    },
  };

  return (
    <UploadContext.Provider value={{ stateUpload, uploadActions }}>
      {children}
    </UploadContext.Provider>
  );
}