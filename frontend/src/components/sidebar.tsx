"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSession, signIn, signOut } from "next-auth/react";
import { clsx } from "clsx";
import {
  LayoutDashboard,
  Swords,
  Dumbbell,
  BarChart3,
  BookOpen,
  UserCircle,
  LogIn,
  LogOut,
} from "lucide-react";

const NAV_ITEMS = [
  { href: "/", label: "Home", icon: LayoutDashboard, requireAuth: false },
  { href: "/games", label: "My Games", icon: Swords, requireAuth: true },
  { href: "/openings", label: "Openings", icon: BookOpen, requireAuth: true },
  { href: "/train", label: "Train", icon: Dumbbell, requireAuth: true },
  { href: "/insights", label: "Insights", icon: BarChart3, requireAuth: true },
  { href: "/profile", label: "Profile", icon: UserCircle, requireAuth: true },
] as const;

export function Sidebar() {
  const pathname = usePathname();
  const { data: session, status } = useSession();

  return (
    <aside className="hidden md:flex w-[220px] flex-col border-r border-surface-3 bg-surface-1">
      {/* Logo */}
      <div className="flex items-center gap-2 px-5 py-6">
        <div className="h-8 w-8 rounded-lg bg-brand-600 flex items-center justify-center text-white font-bold text-sm">
          ♔
        </div>
        <span className="text-lg font-semibold tracking-tight">
          Chess Analyzer
        </span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 space-y-1">
        {NAV_ITEMS
          .filter(({ requireAuth }) => !requireAuth || !!session)
          .map(({ href, label, icon: Icon }) => {
          const isActive =
            href === "/" ? pathname === "/" : pathname.startsWith(href);

          return (
            <Link
              key={href}
              href={href}
              className={clsx(
                "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors",
                isActive
                  ? "bg-brand-600/20 text-brand-400"
                  : "text-gray-400 hover:bg-surface-2 hover:text-white"
              )}
            >
              <Icon className="h-4 w-4" />
              {label}
            </Link>
          );
        })}
      </nav>

      {/* Auth */}
      <div className="px-3 pb-4 border-t border-surface-3 pt-4">
        {status === "loading" ? (
          <div className="px-3 py-2 text-sm text-gray-500">Loading...</div>
        ) : session?.user ? (
          <div className="space-y-2">
            <div className="px-3 text-sm text-gray-400 truncate">
              {session.user.email}
            </div>
            <button
              onClick={() => signOut()}
              className="flex items-center gap-2 w-full px-3 py-2 rounded-lg text-sm text-gray-400 hover:bg-surface-2 hover:text-white transition-colors"
            >
              <LogOut className="h-4 w-4" />
              Sign Out
            </button>
          </div>
        ) : (
          <button
            onClick={() => signIn()}
            className="flex items-center gap-2 w-full px-3 py-2.5 rounded-lg text-sm font-medium bg-brand-600 text-white hover:bg-brand-700 transition-colors"
          >
            <LogIn className="h-4 w-4" />
            Sign Up
          </button>
        )}
      </div>
    </aside>
  );
}
