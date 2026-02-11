/**
 * Auth helpers for attaching NextAuth JWT to API requests.
 *
 * In server components / route handlers, use getServerSession.
 * In client components, use getSession() from next-auth/react.
 */

import { getSession } from "next-auth/react";

/**
 * Get headers with the Authorization bearer token from the current session.
 * Returns empty object when not authenticated.
 */
export async function getAuthHeaders(): Promise<Record<string, string>> {
  const session = await getSession();

  if (!session) {
    return {};
  }

  // NextAuth exposes the raw JWT through the session token endpoint.
  // We fetch /api/auth/session and use the internal JWT.
  // Since we're using the "jwt" strategy, the JWT is available as a cookie.
  // For API calls via fetchAPI, we'll pull the raw token from
  // the NextAuth internal token endpoint.
  const res = await fetch("/api/auth/token", { credentials: "include" });
  if (res.ok) {
    const data = await res.json();
    if (data?.token) {
      return { Authorization: `Bearer ${data.token}` };
    }
  }

  return {};
}
