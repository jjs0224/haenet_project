// Safe storage helpers for environments that block Web Storage (e.g., Brave shields).
const sessionMem = new Map();
const localMem = new Map();

function toStr(value) {
  return value == null ? "" : String(value);
}

export const safeSession = {
  get(key) {
    try {
      return sessionStorage.getItem(key);
    } catch {
      return sessionMem.get(key) ?? null;
    }
  },
  set(key, value) {
    try {
      sessionStorage.setItem(key, toStr(value));
    } catch {
      sessionMem.set(key, toStr(value));
    }
  },
  remove(key) {
    try {
      sessionStorage.removeItem(key);
    } catch {
      sessionMem.delete(key);
    }
  },
};

export const safeLocal = {
  get(key) {
    try {
      return localStorage.getItem(key);
    } catch {
      return localMem.get(key) ?? null;
    }
  },
  set(key, value) {
    try {
      localStorage.setItem(key, toStr(value));
    } catch {
      localMem.set(key, toStr(value));
    }
  },
  remove(key) {
    try {
      localStorage.removeItem(key);
    } catch {
      localMem.delete(key);
    }
  },
};
