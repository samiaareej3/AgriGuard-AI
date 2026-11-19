"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, getToken, setToken } from "./api";
import type { Role, TokenResponse, User } from "./types";

const RANK: Record<Role, number> = { viewer: 0, operator: 1, admin: 2 };

interface AuthState {
  user: User | null;
  status: "loading" | "authenticated" | "anonymous";
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  refresh: () => Promise<void>;
  can: (role: Role) => boolean;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<AuthState["status"]>("loading");
  const qc = useQueryClient();

  const refresh = useCallback(async () => {
    if (!getToken()) {
      setUser(null);
      setStatus("anonymous");
      return;
    }
    try {
      setUser(await api<User>("/auth/me"));
      setStatus("authenticated");
    } catch {
      setUser(null);
      setStatus("anonymous");
    }
  }, []);

  useEffect(() => {
    refresh();
    const onUnauthorized = () => {
      setUser(null);
      setStatus("anonymous");
    };
    window.addEventListener("agriguard:unauthorized", onUnauthorized);
    return () => window.removeEventListener("agriguard:unauthorized", onUnauthorized);
  }, [refresh]);

  const login = useCallback(async (username: string, password: string) => {
    const res = await api<TokenResponse>("/auth/login", { body: { username, password } });
    setToken(res.access_token);
    setUser(res.user);
    setStatus("authenticated");
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
    setStatus("anonymous");
    qc.clear();
  }, [qc]);

  const can = useCallback((role: Role) => !!user && RANK[user.role] >= RANK[role], [user]);

  const value = useMemo(() => ({ user, status, login, logout, refresh, can }), [user, status, login, logout, refresh, can]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
