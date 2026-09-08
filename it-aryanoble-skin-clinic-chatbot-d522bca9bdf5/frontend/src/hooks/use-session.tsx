"use client";

import React, { createContext, useContext } from "react";
import { useCurrentUser } from "./use-current-user";
import type { UserResponse } from "@/lib/types";

interface AuthContextType {
  user: UserResponse | null;
  isLoading: boolean;
  isError: boolean;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  isLoading: true,
  isError: false,
});

export const AuthProvider = ({ children }: { children: React.ReactNode }) => {
  const { data: user, isLoading, isError } = useCurrentUser();

  return (
    <AuthContext.Provider value={{ user: user || null, isLoading, isError }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useSession = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useSession must be used within an AuthProvider");
  }
  return context;
};
