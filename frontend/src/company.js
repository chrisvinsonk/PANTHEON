const STORAGE_KEY = "pantheon.activeCompanyId";

export function getActiveCompanyId() {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  const parsed = Number(raw);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

export function setActiveCompanyId(companyId) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, String(companyId));
}

export function clearActiveCompanyId() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(STORAGE_KEY);
}

export function activeCompanyHeaders() {
  const companyId = getActiveCompanyId();
  return companyId ? { "X-Company-Id": String(companyId) } : {};
}

export function switchActiveCompany(companyId) {
  setActiveCompanyId(companyId);
  if (typeof window !== "undefined") {
    window.location.reload();
  }
}
