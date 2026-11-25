import { ClerkProvider } from "@clerk/react";
import React from "react";
import { createRoot } from "react-dom/client";
import { shadcn } from "@clerk/ui/themes";
import App from "./App";
import { homeUrl, signInUrl, signUpUrl } from "./auth";
import { TooltipProvider } from "@/components/ui/tooltip";
import "./styles.css";
const publishableKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

if (!publishableKey) {
  document.getElementById("root").innerHTML =
    '<div style="padding:2rem;font-family:sans-serif;color:#f5f2e9;background:#0a0a09;min-height:100vh">Missing VITE_CLERK_PUBLISHABLE_KEY. Set it in Vercel and redeploy.</div>';
  throw new Error("Missing VITE_CLERK_PUBLISHABLE_KEY");
}

// Auth must always return to the origin the app is actually served from. Clerk
// falls back to the instance's configured home URL when no explicit redirect is
// given, which is how a production build ended up redirecting to localhost:5174.
// Deriving the URL from window.location keeps dev (5174), Render and any custom
// domain correct without rebuilding or editing the Clerk dashboard.

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <ClerkProvider
      publishableKey={publishableKey}
      afterSignOutUrl={homeUrl}
      signInUrl={signInUrl}
      signUpUrl={signUpUrl}
      signInFallbackRedirectUrl={homeUrl}
      signUpFallbackRedirectUrl={homeUrl}
      appearance={{
        theme: shadcn,
        variables: {
          borderRadius: "8px",
          colorBackground: "#11110f",
          colorBorder: "#34332d",
          colorForeground: "#f5f2e9",
          colorInput: "#0a0a09",
          colorMuted: "#1a1915",
          colorMutedForeground: "#a7a293",
          colorNeutral: "#d4af37",
          colorPrimary: "#d4af37",
          colorPrimaryForeground: "#080808",
        },
      }}
    >
      <TooltipProvider>
        <App />
      </TooltipProvider>
    </ClerkProvider>
  </React.StrictMode>,
);