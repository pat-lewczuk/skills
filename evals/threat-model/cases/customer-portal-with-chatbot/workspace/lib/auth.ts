import NextAuth from "next-auth";
import Credentials from "next-auth/providers/credentials";
import bcrypt from "bcryptjs";
import { db } from "./db";

export const { handlers, auth, signIn, signOut } = NextAuth({
  session: { strategy: "jwt" },
  providers: [
    Credentials({
      credentials: { email: {}, password: {} },
      async authorize(creds) {
        const user = await db.user.findUnique({ where: { email: String(creds.email) } });
        if (!user) return null;
        const ok = await bcrypt.compare(String(creds.password), user.passwordHash);
        return ok ? { id: user.id, email: user.email } : null;
      },
    }),
  ],
  callbacks: {
    async jwt({ token, user }) {
      if (user) {
        const u = await db.user.findUniqueOrThrow({ where: { id: user.id! } });
        token.userId = u.id;
        token.organizationId = u.organizationId;
        token.role = u.role;
      }
      return token;
    },
    async session({ session, token }) {
      session.user.id = token.userId as string;
      (session.user as any).organizationId = token.organizationId;
      (session.user as any).role = token.role;
      return session;
    },
  },
});

export async function requireUser() {
  const session = await auth();
  if (!session?.user) throw new Response("Unauthorized", { status: 401 });
  const u = session.user as any;
  return { id: u.id as string, organizationId: u.organizationId as string, role: u.role as "ADMIN" | "MEMBER" };
}
