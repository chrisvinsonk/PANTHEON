import { useEffect, useState } from "react";
import {
  AuthenticateWithRedirectCallback,
  SignIn,
  SignUp,
  useAuth,
} from "@clerk/react";
import Landing from "./components/Landing";
import Dashboard from "./components/Dashboard";
import Onboarding from "./components/Onboarding";
import { getCompany } from "./api";
import { homeUrl, signInUrl, signUpUrl } from "./auth";
import "./styles.css";

// The app has no router: Clerk's own routes are matched on the URL so the OAuth
// callback can be completed here, on the origin that served the page. Before
// this existed, Clerk finished the OAuth round trip on its hosted Account
// Portal, which then redirected to the instance home URL (localhost:5174).

/** Centers a Clerk component in the same shell the landing page uses. */
function AuthShell({ children }) {
  return (
    <div className="app-shell flex min-h-svh items-center justify-center px-6 py-16">
      {children}
    </div>
  );
}

function SSOCallbackRoute() {
  return (
    <AuthShell>
      <AuthenticateWithRedirectCallback
        signInUrl={signInUrl}
        signUpUrl={signUpUrl}
        signInFallbackRedirectUrl={homeUrl}
        signUpFallbackRedirectUrl={homeUrl}
      />
    </AuthShell>
  );
}

export default function App() {
  const { isLoaded, isSignedIn, getToken } = useAuth();
  const [needsOnboarding, setNeedsOnboarding] = useState(false);
  const [checked, setChecked] = useState(false);
  const pathname = window.location.pathname;
  // Clerk appends its routes as a hash when it builds the sign-in URL, so the
  // callback can arrive as /sign-in#/sso-callback as well as /sso-callback.
  useEffect(() => {
    if (!isLoaded || !isSignedIn) return;
    let cancelled = false;
    (async () => {
      try {
        const token = await getToken();
        const company = await getCompany(token);
        if (!cancelled && company && company.onboarded === false) {
          setNeedsOnboarding(true);
        }
      } catch (e) {
        // ignore; dashboard will handle
      } finally {
        if (!cancelled) setChecked(true);
      }
    })();
    return () => { cancelled = true; };
  }, [isLoaded, isSignedIn, getToken]);

  const isSSOCallback =
    pathname.startsWith("/sso-callback") ||
    window.location.hash.includes("sso-callback");

  if (isSSOCallback) return <SSOCallbackRoute />;

  if (pathname.startsWith("/sign-in")) {
    return (
      <AuthShell>
        <SignIn routing="path" path="/sign-in" fallbackRedirectUrl={homeUrl} />
      </AuthShell>
    );
  }

  if (pathname.startsWith("/sign-up")) {
    return (
      <AuthShell>
        <SignUp routing="path" path="/sign-up" fallbackRedirectUrl={homeUrl} />
      </AuthShell>
    );
  }

  if (!isLoaded) {
    return (
      <div className="app-shell flex min-h-svh items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary/30 border-t-primary" />
      </div>
    );
  }

  if (isSignedIn && needsOnboarding) {
    return <Onboarding getToken={getToken} onComplete={() => setNeedsOnboarding(false)} />;
  }

  if (isSignedIn) return <Dashboard />;

  return (
    <div className="app-shell">
      <Landing />
    </div>
  );
}
