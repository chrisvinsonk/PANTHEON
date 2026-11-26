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
import { getCompanies } from "./api";
import {
  clearActiveCompanyId,
  isBlankCompany,
  syncActiveCompanyId,
} from "./company";
import { homeUrl, signInUrl, signUpUrl } from "./auth";
import "./styles.css";

// The app has no router: Clerk's own routes are matched on the URL so the OAuth
// callback can be completed here, on the origin that served the page.

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

function Loading() {
  return (
    <div className="app-shell flex min-h-svh items-center justify-center">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary/30 border-t-primary" />
    </div>
  );
}

const INITIAL_STATE = {
  checked: false,
  needsOnboarding: false,
  blankCompanyId: null,
  error: "",
};

export default function App() {
  const { isLoaded, isSignedIn, getToken } = useAuth();
  const [state, setState] = useState(INITIAL_STATE);
  const [recheck, setRecheck] = useState(0);
  const pathname = window.location.pathname;

  // The server is the single source of truth for whether this account has a
  // company. No localStorage "onboarded" flag: it was the reason the wizard
  // kept coming back after logout/login.
  useEffect(() => {
    if (!isLoaded || !isSignedIn) {
      setState(INITIAL_STATE);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const token = await getToken();
        const companies = await getCompanies(token);
        if (cancelled) return;
        const usable = companies.filter((company) => !isBlankCompany(company));
        if (usable.length) {
          syncActiveCompanyId(usable);
          setState({
            checked: true,
            needsOnboarding: false,
            blankCompanyId: null,
            error: "",
          });
        } else {
          // Only an unnamed placeholder exists (or nothing at all). Let the
          // wizard fill that row in place instead of leaving a blank behind.
          clearActiveCompanyId();
          setState({
            checked: true,
            needsOnboarding: true,
            blankCompanyId: companies[0]?.id ?? null,
            error: "",
          });
        }
      } catch (error) {
        if (!cancelled) {
          setState({ ...INITIAL_STATE, checked: true, error: error.message });
        }
      }
    })();
    return () => { cancelled = true; };
  }, [isLoaded, isSignedIn, getToken, recheck]);

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

  if (!isLoaded) return <Loading />;

  if (!isSignedIn) {
    return (
      <div className="app-shell">
        <Landing />
      </div>
    );
  }

  if (!state.checked) return <Loading />;

  if (state.error) {
    return (
      <AuthShell>
        <div className="max-w-md space-y-4 text-center">
          <p className="text-sm text-destructive">{state.error}</p>
          <button
            type="button"
            className="rounded-md border border-primary/30 px-4 py-2 text-sm text-primary"
            onClick={() => {
              setState(INITIAL_STATE);
              setRecheck((value) => value + 1);
            }}
          >
            Retry
          </button>
        </div>
      </AuthShell>
    );
  }

  if (state.needsOnboarding) {
    return (
      <Onboarding
        getToken={getToken}
        blankCompanyId={state.blankCompanyId}
        onComplete={() => setRecheck((value) => value + 1)}
      />
    );
  }

  return <Dashboard />;
}
