import {
  createContext,
  useContext,
  useState,
  useEffect,
  ReactNode,
} from "react";
import { User, LoginCredentials, RegisterData } from "../api/types";
import { apiFetch, setAccessToken } from "../api/http";

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  login: (credentials: LoginCredentials) => Promise<void>;
  register: (data: RegisterData) => Promise<void>;
  logout: () => Promise<void>;
  updateProfile: (data: {
    programming_level: number;
    maths_level: number;
  }) => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // On mount, try to restore session via refresh token
  useEffect(() => {
    async function restoreSession() {
      try {
        const response = await fetch("/api/auth/refresh", {
          method: "POST",
          credentials: "include",
        });
        if (response.ok) {
          const data = await response.json();
          setAccessToken(data.access_token);
          const userProfile = await apiFetch<User>("/api/auth/me");
          setUser(userProfile);
        }
      } catch {
        // Session expired or no refresh token
        setAccessToken(null);
      } finally {
        setIsLoading(false);
      }
    }
    restoreSession();
  }, []);

  const login = async (credentials: LoginCredentials) => {
    const data = await apiFetch<{ access_token: string }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify(credentials),
    });
    setAccessToken(data.access_token);
    const userProfile = await apiFetch<User>("/api/auth/me");
    setUser(userProfile);
  };

  const register = async (registerData: RegisterData) => {
    const data = await apiFetch<{ access_token: string }>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify(registerData),
    });
    setAccessToken(data.access_token);
    const userProfile = await apiFetch<User>("/api/auth/me");
    setUser(userProfile);
  };

  const logout = async () => {
    await fetch("/api/auth/logout", { method: "POST", credentials: "include" });
    setAccessToken(null);
    setUser(null);
  };

  const updateProfile = async (data: {
    programming_level: number;
    maths_level: number;
  }) => {
    const updatedUser = await apiFetch<User>("/api/auth/me", {
      method: "PUT",
      body: JSON.stringify(data),
    });
    setUser(updatedUser);
  };

  return (
    <AuthContext.Provider
      value={{ user, isLoading, login, register, logout, updateProfile }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
