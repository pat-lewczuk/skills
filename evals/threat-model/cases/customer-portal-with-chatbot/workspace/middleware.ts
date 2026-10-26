export { auth as middleware } from "@/lib/auth";

export const config = {
  matcher: ["/((?!api/auth|login|_next/static|favicon.ico).*)"],
};
