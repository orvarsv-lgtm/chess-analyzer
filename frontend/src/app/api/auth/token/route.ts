/**
 * Token API route — exposes the raw JWT for use in API requests to the backend.
 *
 * The NextAuth "jwt" strategy stores a signed JWT in an httpOnly cookie.
 * This endpoint decodes it and returns the raw token so the frontend API
 * client can send it as a Bearer token to the FastAPI backend.
 */

import { getToken } from "next-auth/jwt";
import { NextRequest, NextResponse } from "next/server";

export async function GET(req: NextRequest) {
  const token = await getToken({ req, raw: true });

  if (!token) {
    return NextResponse.json({ token: null }, { status: 401 });
  }

  return NextResponse.json({ token });
}
