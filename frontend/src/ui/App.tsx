import { type ReactElement, useCallback, useEffect, useRef, useState } from "react";

import { getWallet, type WalletResponse } from "../api/auth";
import { getCapabilities } from "../api/capabilities";
import {
  AUTHENTICATION_EXPIRED_MESSAGE,
  isAuthenticationExpiredError,
} from "../api/errors";
import { ADDONS } from "../features/registry";
import type { FrontendAddon } from "../features/types";
import { formatDuration, formatRupees } from "./format";
import { useVoiceSession } from "./hooks/useVoiceSession";
import { AdminPage } from "./pages/AdminPage";
import { CallPage } from "./pages/CallPage";
import { GuardrailsPage } from "./pages/GuardrailsPage";
import { HomePage } from "./pages/HomePage";
import { LoginPage } from "./pages/LoginPage";
import { UsagePage } from "./pages/UsagePage";
import { WalletPage } from "./pages/WalletPage";
import "./tokens.css";

type CorePage = "call" | "wallet" | "usage" | "guardrails" | "admin";
type Page = CorePage | string;

type Toast = { id: number; message: string };

const NAV_ICONS: Record<CorePage, ReactElement> = {
  call: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ flexShrink: 0 }}>
      <circle cx="8" cy="8" r="5.5" />
      <circle cx="8" cy="8" r="1.5" fill="currentColor" stroke="none" />
    </svg>
  ),
  wallet: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ flexShrink: 0 }}>
      <rect x="1.5" y="3.5" width="13" height="9" rx="2" />
      <line x1="10" y1="8" x2="12" y2="8" strokeLinecap="round" />
    </svg>
  ),
  usage: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" style={{ flexShrink: 0 }}>
      <line x1="3" y1="13" x2="3" y2="8" />
      <line x1="8" y1="13" x2="8" y2="3.5" />
      <line x1="13" y1="13" x2="13" y2="10" />
    </svg>
  ),
  guardrails: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" style={{ flexShrink: 0 }}>
      <path d="M8 1.8 L13.5 3.8 V8 C13.5 11.3 11.2 13.6 8 14.5 C4.8 13.6 2.5 11.3 2.5 8 V3.8 Z" />
    </svg>
  ),
  admin: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
      <polyline points="1.5,8 5,8 6.5,4.5 9.5,11.5 11,8 14.5,8" />
    </svg>
  ),
};

function Skeleton() {
  const shimmer = {
    background: "linear-gradient(90deg,#EFEFEB 25%,#F2F2EE 37%,#EFEFEB 63%)",
    backgroundSize: "420px 100%",
    animation: "shimmer 1.3s linear infinite",
  };
  return (
    <div style={{ padding: 40, maxWidth: 1040, margin: "0 auto", boxSizing: "border-box" }}>
      <div style={{ height: 30, width: 220, borderRadius: 8, ...shimmer }} />
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 16, marginTop: 28 }}>
        <div style={{ height: 110, borderRadius: 14, ...shimmer }} />
        <div style={{ height: 110, borderRadius: 14, ...shimmer }} />
        <div style={{ height: 110, borderRadius: 14, ...shimmer }} />
      </div>
      <div style={{ height: 320, borderRadius: 14, marginTop: 16, ...shimmer }} />
    </div>
  );
}

export function App() {
  const [token, setToken] = useState(() => localStorage.getItem("nirdeshai_token") ?? "");
  const [email, setEmail] = useState(() => localStorage.getItem("nirdeshai_email") ?? "");
  const [page, setPage] = useState<Page>("call");
  const [navCollapsed, setNavCollapsed] = useState(false);
  const [pageLoading, setPageLoading] = useState(false);
  const [wallet, setWallet] = useState<WalletResponse | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [pendingSessionId, setPendingSessionId] = useState<string | null>(null);
  const [enabledAddons, setEnabledAddons] = useState<FrontendAddon[]>([]);
  // Unauthenticated visitors land on the marketing Home screen at "/";
  // the login screen lives at "/login" so the browser back button works.
  const [landing, setLanding] = useState(() => window.location.pathname !== "/login");
  const toastCounter = useRef(0);
  const loadTimer = useRef<number | null>(null);
  const authExpirationHandled = useRef(false);

  useEffect(() => {
    const onPopState = () => setLanding(window.location.pathname !== "/login");
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  useEffect(() => {
    if (token && window.location.pathname === "/login") {
      window.history.replaceState(null, "", "/");
    }
  }, [token]);

  const pushToast = useCallback((message: string) => {
    const id = ++toastCounter.current;
    setToasts((current) => [...current, { id, message }]);
    window.setTimeout(() => {
      setToasts((current) => current.filter((toast) => toast.id !== id));
    }, 3400);
  }, []);

  const handleAuthenticationExpired = useCallback(() => {
    if (authExpirationHandled.current) return;
    authExpirationHandled.current = true;
    localStorage.removeItem("nirdeshai_token");
    localStorage.removeItem("nirdeshai_email");
    setToken("");
    setEmail("");
    setWallet(null);
    setPage("call");
    window.history.replaceState(null, "", "/login");
    setLanding(false);
    pushToast(AUTHENTICATION_EXPIRED_MESSAGE);
  }, [pushToast]);

  const refreshWallet = useCallback(() => {
    if (!token) return;
    getWallet(token)
      .then(setWallet)
      .catch((error: unknown) => {
        if (isAuthenticationExpiredError(error)) handleAuthenticationExpired();
        else pushToast(String(error));
      });
  }, [token, pushToast, handleAuthenticationExpired]);

  const onBalanceChange = useCallback((balancePaise: number) => {
    setWallet((current) => (current ? { ...current, balance_paise: balancePaise } : current));
  }, []);

  const session = useVoiceSession(token, onBalanceChange, handleAuthenticationExpired);

  useEffect(() => {
    refreshWallet();
  }, [refreshWallet]);

  useEffect(() => {
    let active = true;
    getCapabilities()
      .then((capabilities) => {
        if (active) setEnabledAddons(ADDONS.filter((addon) => addon.isEnabled(capabilities)));
      })
      .catch(() => {
        if (active) setEnabledAddons([]);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const isAddonPage = ADDONS.some((addon) => addon.id === page);
    const isEnabled = enabledAddons.some((addon) => addon.id === page);
    if (isAddonPage && !isEnabled) setPage("call");
  }, [enabledAddons, page]);

  // Refresh the ledger after a call ends so usage debits appear.
  const callStatus = session.state.callStatus;
  useEffect(() => {
    if (callStatus === "ended") refreshWallet();
  }, [callStatus, refreshWallet]);

  const navigate = useCallback((target: Page) => {
    if (loadTimer.current != null) window.clearTimeout(loadTimer.current);
    setPage(target);
    if (target === "call") {
      setPageLoading(false);
      return;
    }
    setPageLoading(true);
    loadTimer.current = window.setTimeout(() => {
      setPageLoading(false);
      loadTimer.current = null;
    }, 480);
  }, []);

  const goWallet = useCallback(() => navigate("wallet"), [navigate]);

  const openSessionInUsage = useCallback(
    (sessionId: string) => {
      setPendingSessionId(sessionId);
      navigate("usage");
    },
    [navigate],
  );

  function logout() {
    void session.stop();
    localStorage.removeItem("nirdeshai_token");
    localStorage.removeItem("nirdeshai_email");
    setToken("");
    setEmail("");
    setWallet(null);
    setPage("call");
    window.history.pushState(null, "", "/");
    setLanding(true);
    authExpirationHandled.current = false;
  }

  if (!token) {
    return (
      <>
        {landing ? (
          <HomePage
            onLogin={() => {
              window.history.pushState(null, "", "/login");
              setLanding(false);
              window.scrollTo(0, 0);
            }}
          />
        ) : (
          <LoginPage
            onAuthenticated={(newToken, newEmail) => {
              authExpirationHandled.current = false;
              localStorage.setItem("nirdeshai_token", newToken);
              localStorage.setItem("nirdeshai_email", newEmail);
              window.history.replaceState(null, "", "/");
              setToken(newToken);
              setEmail(newEmail);
              setPage("call");
            }}
            pushToast={pushToast}
          />
        )}
        <ToastStack toasts={toasts} />
      </>
    );
  }

  const balance = wallet?.balance_paise ?? session.state.balancePaise;
  const globalLowBal =
    balance != null && (balance < 100 || session.state.lowBalance) && page !== "wallet";
  const callLive = session.state.callStatus === "active";
  const selectedAddon = enabledAddons.find((addon) => addon.id === page);

  const navItem = (target: Page, label: string, icon: ReactElement) => {
    const isActive = page === target;
    return (
      <button
        key={target}
        type="button"
        onClick={() => navigate(target)}
        title={label}
        className={isActive ? undefined : "hovGhost"}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          width: "100%",
          padding: "8px 10px",
          border: "none",
          borderRadius: 8,
          background: isActive ? "#E9E9E4" : "transparent",
          color: isActive ? "#111110" : "#5C5C57",
          fontSize: 13.5,
          fontWeight: 500,
          textAlign: "left",
          justifyContent: navCollapsed ? "center" : "flex-start",
        }}
      >
        {icon}
        {!navCollapsed && <span style={{ flex: 1 }}>{label}</span>}
        {target === "call" && callLive && (
          <span style={{ display: "inline-flex", alignItems: "center", gap: 5, flexShrink: 0 }}>
            <span
              style={{
                width: 7,
                height: 7,
                borderRadius: "50%",
                background: "#22A45D",
                animation: "blinkDot 1.4s infinite",
              }}
            />
            {!navCollapsed && (
              <span style={{ fontSize: 11, color: "#1F7A46", fontVariantNumeric: "tabular-nums" }}>
                {formatDuration(session.state.elapsedSeconds)}
              </span>
            )}
          </span>
        )}
      </button>
    );
  };

  return (
    <div style={{ display: "flex", height: "100vh", overflow: "hidden", background: "#F7F7F5" }}>
      <aside
        style={{
          width: navCollapsed ? 76 : 216,
          flexShrink: 0,
          display: "flex",
          flexDirection: "column",
          borderRight: "1px solid #E5E5E1",
          padding: "20px 12px 16px",
          boxSizing: "border-box",
          transition: "width .2s ease",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 6,
            padding: "0 4px 20px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 9, minWidth: 0 }}>
            <div
              style={{
                width: 22,
                height: 22,
                borderRadius: 7,
                background: "#111110",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 2,
                flexShrink: 0,
              }}
            >
              <span style={{ width: 2, height: 7, borderRadius: 1, background: "#FFFFFF" }} />
              <span style={{ width: 2, height: 11, borderRadius: 1, background: "#FFFFFF" }} />
              <span style={{ width: 2, height: 5, borderRadius: 1, background: "#FFFFFF" }} />
            </div>
            {!navCollapsed && (
              <div
                style={{
                  fontSize: 14,
                  fontWeight: 600,
                  letterSpacing: "-0.01em",
                  whiteSpace: "nowrap",
                }}
              >
                Nirdesh<span style={{ color: "#4A6CF7" }}>AI</span>
              </div>
            )}
          </div>
          <button
            type="button"
            onClick={() => setNavCollapsed(!navCollapsed)}
            title="Toggle sidebar"
            className="hovFg"
            style={{
              border: "none",
              background: "none",
              color: "#A6A6A0",
              fontSize: 13,
              padding: "2px 4px",
              flexShrink: 0,
            }}
          >
            {navCollapsed ? "»" : "«"}
          </button>
        </div>
        <nav style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          {navItem("call", "Call", NAV_ICONS.call)}
          {navItem("wallet", "Wallet", NAV_ICONS.wallet)}
          {navItem("usage", "Usage", NAV_ICONS.usage)}
          {enabledAddons.map((addon) => navItem(addon.id, addon.label, addon.icon))}
          {!navCollapsed ? (
            <div
              style={{
                fontSize: 10.5,
                fontWeight: 600,
                letterSpacing: "0.09em",
                textTransform: "uppercase",
                color: "#A6A6A0",
                padding: "18px 10px 6px",
              }}
            >
              Operations
            </div>
          ) : (
            <div style={{ height: 1, background: "#E5E5E1", margin: "14px 8px 8px" }} />
          )}
          {navItem("guardrails", "Guardrails", NAV_ICONS.guardrails)}
          {navItem("admin", "Admin", NAV_ICONS.admin)}
        </nav>
        <div style={{ flex: 1 }} />
        <div
          style={{
            borderTop: "1px solid #E5E5E1",
            padding: "12px 10px 0",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 8,
          }}
        >
          {!navCollapsed && (
            <div
              style={{
                fontSize: 12,
                color: "#6B6B66",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {email}
            </div>
          )}
          <button
            type="button"
            onClick={logout}
            className="hovUnderline"
            style={{
              border: "none",
              background: "none",
              color: "#4A6CF7",
              fontSize: 12,
              padding: 0,
              flexShrink: 0,
            }}
          >
            Log out
          </button>
        </div>
      </aside>

      <main style={{ flex: 1, overflowY: "auto", position: "relative", minWidth: 0 }}>
        {globalLowBal && balance != null && (
          <div
            style={{
              position: "sticky",
              top: 0,
              zIndex: 45,
              display: "flex",
              alignItems: "center",
              gap: 10,
              padding: "9px 24px",
              background: "#FCF6E8",
              borderBottom: "1px solid #EED9A8",
              color: "#8A5E06",
              fontSize: 12.5,
            }}
          >
            <span
              style={{
                width: 7,
                height: 7,
                borderRadius: "50%",
                background: "currentColor",
                animation: "blinkDot 1.4s infinite",
                flexShrink: 0,
              }}
            />
            <span style={{ flex: 1 }}>
              Wallet balance {formatRupees(balance)} — voice calls end automatically at ₹0.00.
            </span>
            <button
              type="button"
              onClick={goWallet}
              style={{
                border: "none",
                background: "none",
                color: "inherit",
                fontWeight: 600,
                textDecoration: "underline",
                padding: 0,
                flexShrink: 0,
              }}
            >
              Top up
            </button>
          </div>
        )}

        {pageLoading ? (
          <Skeleton />
        ) : page === "call" ? (
          <CallPage
            session={session}
            goWallet={goWallet}
            walletBalancePaise={wallet?.balance_paise ?? null}
          />
        ) : page === "wallet" ? (
          <WalletPage
            token={token}
            wallet={wallet}
            onWalletChanged={refreshWallet}
            pushToast={pushToast}
            openSession={openSessionInUsage}
            onAuthenticationExpired={handleAuthenticationExpired}
          />
        ) : page === "usage" ? (
          <UsagePage
            token={token}
            openSessionId={pendingSessionId}
            onSessionOpened={() => setPendingSessionId(null)}
            pushToast={pushToast}
            onAuthenticationExpired={handleAuthenticationExpired}
          />
        ) : selectedAddon ? (
          selectedAddon.render({
            token,
            pushToast,
            onAuthenticationExpired: handleAuthenticationExpired,
          })
        ) : page === "guardrails" ? (
          <GuardrailsPage />
        ) : (
          <AdminPage />
        )}
      </main>

      <ToastStack toasts={toasts} />
    </div>
  );
}

function ToastStack({ toasts }: { toasts: Toast[] }) {
  return (
    <div
      style={{
        position: "fixed",
        right: 24,
        bottom: 24,
        display: "flex",
        flexDirection: "column",
        gap: 8,
        zIndex: 120,
      }}
    >
      {toasts.map((toast) => (
        <div
          key={toast.id}
          style={{
            background: "#FFFFFF",
            border: "1px solid #E5E5E1",
            borderRadius: 12,
            padding: "11px 16px",
            fontSize: 13,
            boxShadow: "0 16px 40px -18px rgba(17,17,16,0.35)",
            animation: "toastIn .22s ease",
            display: "flex",
            alignItems: "center",
            gap: 14,
          }}
        >
          <span>{toast.message}</span>
        </div>
      ))}
    </div>
  );
}
