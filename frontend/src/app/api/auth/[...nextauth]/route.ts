import NextAuth from "next-auth";
import GoogleProvider from "next-auth/providers/google";
import CredentialsProvider from "next-auth/providers/credentials";

const providers: any[] = [];

// ── Dev-mode credentials (always available for local testing) ──
providers.push(
  CredentialsProvider({
    name: "Dev Login",
    credentials: {
      email: { label: "Email", type: "email", placeholder: "you@example.com" },
    },
    async authorize(credentials, req) {
      // In dev mode, any email creates a session. No password needed.
      const email = credentials?.email as string | undefined;
      if (!email) return null;
      return {
        id: email,
        email: email,
        name: email.split("@")[0],
      };
    },
  })
);

// ── Google OAuth (only if configured) ──
if (process.env.GOOGLE_CLIENT_ID && process.env.GOOGLE_CLIENT_SECRET) {
  providers.push(
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET,
    })
  );
}

const handler = NextAuth({
  providers,

  session: {
    strategy: "jwt",
  },

  callbacks: {
    async jwt({ token, user }) {
      if (user) {
        token.id = user.id;
        token.email = user.email;
      }
      return token;
    },
    async session({ session, token }) {
      if (session.user) {
        (session.user as any).id = token.id;
        session.user.email = token.email as string;
      }
      return session;
    },
  },

  pages: {
    signIn: "/auth/signin",
  },

  secret: process.env.NEXTAUTH_SECRET,
});

export { handler as GET, handler as POST };
