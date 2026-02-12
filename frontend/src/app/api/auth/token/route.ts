/**
 * Token API route — creates a plain HS256-signed JWT from the NextAuth session
 * that the FastAPI backend can verify with the shared NEXTAUTH_SECRET.
 *
 * NextAuth stores tokens as encrypted JWE cookies which the Python backend
 * cannot decode. This endpoint decrypts the cookie, extracts the claims,
 * and re-signs them as a standard HS256 JWT.
 */

import { getToken } from "next-auth/jwt";
import { NextRequest, NextResponse } from "next/server";
import { SignJWT } from "jose";

export async function GET(req: NextRequest) {
  // Decode (decrypt) the NextAuth cookie — raw: false gives us the payload
  const payload = await getToken({ req });

  if (!payload) {
    return NextResponse.json({ token: null }, { status: 401 });
  }

  const secret = process.env.NEXTAUTH_SECRET;
  if (!secret) {
    return NextResponse.json({ error: "Server misconfigured" }, { status: 500 });
  }

  // Sign a plain HS256 JWT with the claims the backend expects
  const encodedSecret = new TextEncoder().encode(secret);
  const sub = (payload.sub ?? payload.id ?? payload.email) as string | undefined;
  const token = await new SignJWT({
    sub,
    email: payload.email as string,
    name: payload.name as string,
  })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime("1h")
    .sign(encodedSecret);

  return NextResponse.json({ token });
}
