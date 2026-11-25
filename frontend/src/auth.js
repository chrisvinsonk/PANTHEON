// Every auth URL is derived from the origin that actually served the page.
//
// Clerk builds OAuth callback URLs from the instance's *sign-in URL*. On a
// development instance that defaults to the hosted Account Portal
// (*.accounts.dev), and the portal then finishes by sending the browser to the
// instance home URL — which points at whichever dev origin was registered first
// (localhost:5174). Pinning signInUrl/signUpUrl to this origin keeps the whole
// OAuth round trip here, so the deployed app never hands the user to a
// localhost URL and local dev keeps working unchanged.
const origin = typeof window === "undefined" ? "" : window.location.origin;

export const homeUrl = `${origin}/`;
export const signInUrl = `${origin}/sign-in`;
export const signUpUrl = `${origin}/sign-up`;
