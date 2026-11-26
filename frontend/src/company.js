const STORAGE_KEY = "pantheon.activeCompanyId";
const CHANGE_EVENT = "pantheon:company-changed";

function storage() {
  return typeof window === "undefined" ? null : window.localStorage;
}

function emitChange() {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(CHANGE_EVENT));
  }
}

export function onChangeCompany(callback) {
  if (typeof window === "undefined") return () => {};
  window.addEventListener(CHANGE_EVENT, callback);
  return () => window.removeEventListener(CHANGE_EVENT, callback);
}

export function isBlankCompany(company) {
  return !(company?.name || "").trim();
}

export function getActiveCompanyId() {
  const raw = storage()?.getItem(STORAGE_KEY);
  if (!raw) return null;
  const parsed = Number(raw);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

export function setActiveCompanyId(companyId) {
  if (!companyId) return clearActiveCompanyId();
  storage()?.setItem(STORAGE_KEY, String(companyId));
  emitChange();
}

export function clearActiveCompanyId() {
  storage()?.removeItem(STORAGE_KEY);
  emitChange();
}

export function activeCompanyHeaders() {
  const companyId = getActiveCompanyId();
  return companyId ? { "X-Company-Id": String(companyId) } : {};
}

/**
 * Point the active-company header at a company that actually exists and is
 * usable. Returns the id that is now active (or null when there is none).
 * A stale id is repaired in memory — no page reload required.
 */
export function syncActiveCompanyId(companies) {
  const usable = (companies || []).filter((company) => !isBlankCompany(company));
  const stored = getActiveCompanyId();
  const match = usable.find((company) => company.id === stored);
  const next = match ? match.id : usable[0]?.id ?? null;
  if (next !== stored) {
    if (next) storage()?.setItem(STORAGE_KEY, String(next));
    else storage()?.removeItem(STORAGE_KEY);
    emitChange();
  }
  return next;
}
