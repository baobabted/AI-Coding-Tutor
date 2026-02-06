let accessToken: string | null = null;

export function setAccessToken(token: string | null) {
  accessToken = token;
}

export function getAccessToken(): string | null {
  return accessToken;
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const headers = new Headers(options.headers);

  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }
  if (!headers.has("Content-Type") && options.body) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(path, {
    ...options,
    headers,
    credentials: "include",
  });

  // Don't try to refresh token for auth endpoints - just throw the error
  const isAuthEndpoint = path.startsWith("/api/auth/login") ||
                         path.startsWith("/api/auth/register") ||
                         path.startsWith("/api/auth/refresh");

  if (response.status === 401 && !isAuthEndpoint) {
    // Try to refresh the token
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      // Retry original request with new token
      headers.set("Authorization", `Bearer ${accessToken}`);
      const retryResponse = await fetch(path, {
        ...options,
        headers,
        credentials: "include",
      });
      if (!retryResponse.ok) {
        const error = await retryResponse
          .json()
          .catch(() => ({ detail: "Unknown error" }));
        throw new Error(error.detail || `API error: ${retryResponse.status}`);
      }
      return retryResponse.json();
    } else {
      // Redirect to login
      window.location.href = "/login";
      throw new Error("Session expired");
    }
  }

  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ detail: "Unknown error" }));
    throw new Error(error.detail || `API error: ${response.status}`);
  }

  // Handle empty responses (like logout)
  const text = await response.text();
  if (!text) {
    return {} as T;
  }
  return JSON.parse(text);
}

async function refreshAccessToken(): Promise<boolean> {
  try {
    const response = await fetch("/api/auth/refresh", {
      method: "POST",
      credentials: "include",
    });
    if (response.ok) {
      const data = await response.json();
      setAccessToken(data.access_token);
      return true;
    }
    return false;
  } catch {
    return false;
  }
}
