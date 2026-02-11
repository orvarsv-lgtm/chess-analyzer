"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import Link from "next/link";
import {
  Swords,
  Dumbbell,
  BarChart3,
  BookOpen,
  ArrowRight,
  TrendingUp,
  TrendingDown,
  Minus,
} from "lucide-react";
import { insightsAPI, type InsightsOverview, type RecentGame } from "@/lib/api";
import { Card, StatCard, Badge } from "@/components/ui";

export default function HomePage() {
  const { data: session } = useSession();
  const [overview, setOverview] = useState<InsightsOverview | null>(null);
  const [recentGames, setRecentGames] = useState<RecentGame[]>([]);

  useEffect(() => {
    if (session) {
      insightsAPI.overview().then(setOverview).catch(() => {});
      insightsAPI.recentGames(5).then(setRecentGames).catch(() => {});
    }
  }, [session]);

  return (
    <div className="max-w-5xl mx-auto px-6 py-12 animate-fade-in">
      {/* Hero */}
      <div className="text-center space-y-4 mb-12">
        <h1 className="text-4xl md:text-5xl font-bold tracking-tight">
          Analyze your games.
          <br />
          <span className="text-brand-400">Find your weaknesses.</span>
        </h1>
        <p className="text-gray-400 text-lg max-w-2xl mx-auto">
          Import from Lichess or Chess.com. Get engine analysis, personalized
          puzzles, and coaching insights — all in one place.
        </p>
      </div>

      {/* Quick stats for logged-in users */}
      {session && overview && overview.total_games > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          <StatCard
            label="Games"
            value={overview.total_games}
            icon={<Swords className="h-5 w-5" />}
          />
          <StatCard
            label="Overall CPL"
            value={overview.overall_cpl ?? "—"}
            subtitle={
              overview.trend === "improving"
                ? "↗ Improving"
                : overview.trend === "declining"
                ? "↘ Declining"
                : undefined
            }
            trend={
              overview.trend === "improving"
                ? "up"
                : overview.trend === "declining"
                ? "down"
                : "neutral"
            }
          />
          <StatCard
            label="Win Rate"
            value={overview.win_rate ? `${overview.win_rate}%` : "—"}
          />
          <StatCard
            label="Blunders/100"
            value={overview.blunder_rate ?? "—"}
          />
        </div>
      )}

      {/* Quick actions */}
      <div className="grid md:grid-cols-4 gap-4 mb-8">
        <QuickAction
          href="/games"
          icon={Swords}
          title="My Games"
          desc="Import and review your analyzed games"
        />
        <QuickAction
          href="/openings"
          icon={BookOpen}
          title="Openings"
          desc="Your opening repertoire stats"
        />
        <QuickAction
          href="/train"
          icon={Dumbbell}
          title="Train"
          desc="Solve puzzles from your own mistakes"
        />
        <QuickAction
          href="/insights"
          icon={BarChart3}
          title="Insights"
          desc="See your strengths and weaknesses"
        />
      </div>

      {/* Recent activity */}
      {session && recentGames.length > 0 && (
        <div className="mb-16">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold">Recent Games</h2>
            <Link
              href="/games"
              className="text-sm text-brand-400 hover:text-brand-300 flex items-center gap-1"
            >
              View all <ArrowRight className="h-3 w-3" />
            </Link>
          </div>
          <div className="space-y-2">
            {recentGames.map((g) => {
              const date = g.date
                ? new Date(g.date).toLocaleDateString("en-US", {
                    month: "short",
                    day: "numeric",
                  })
                : "";
              return (
                <Link key={g.id} href={`/games/${g.id}`}>
                  <Card className="flex items-center gap-4 px-5 py-3 hover:bg-surface-2/50 transition-colors cursor-pointer">
                    <div
                      className={`h-7 w-7 rounded flex items-center justify-center text-xs font-bold ${
                        g.color === "white"
                          ? "bg-white text-gray-900"
                          : "bg-gray-800 text-white border border-surface-3"
                      }`}
                    >
                      {g.color === "white" ? "♔" : "♚"}
                    </div>
                    <div className="flex-1 min-w-0">
                      <span className="text-sm font-medium truncate">
                        {g.opening_name || "Unknown Opening"}
                      </span>
                      <div className="flex items-center gap-2 text-xs text-gray-500">
                        <span>{date}</span>
                        {g.time_control && <span>{g.time_control}</span>}
                        <span className="capitalize">{g.platform}</span>
                      </div>
                    </div>
                    <Badge
                      variant={
                        g.result === "win"
                          ? "success"
                          : g.result === "loss"
                          ? "danger"
                          : "warning"
                      }
                    >
                      {g.result.toUpperCase()}
                    </Badge>
                    {g.overall_cpl !== null && (
                      <span
                        className={`text-xs font-medium ${
                          g.overall_cpl < 30
                            ? "text-green-400"
                            : g.overall_cpl < 60
                            ? "text-yellow-400"
                            : "text-red-400"
                        }`}
                      >
                        {Math.round(g.overall_cpl)} CPL
                      </span>
                    )}
                  </Card>
                </Link>
              );
            })}
          </div>
        </div>
      )}

      {/* Not signed in prompt */}
      {!session && (
        <div className="text-center py-8 rounded-xl bg-surface-1 border border-surface-3">
          <p className="text-gray-400 mb-4">
            Sign in to start analyzing your games.
          </p>
          <Link
            href="/api/auth/signin"
            className="inline-flex items-center gap-2 px-6 py-3 bg-brand-600 text-white rounded-lg font-medium hover:bg-brand-700 transition-colors"
          >
            Get Started <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      )}
    </div>
  );
}

function QuickAction({
  href,
  icon: Icon,
  title,
  desc,
}: {
  href: string;
  icon: any;
  title: string;
  desc: string;
}) {
  return (
    <Link
      href={href}
      className="group flex flex-col gap-3 p-5 rounded-xl bg-surface-1 border border-surface-3 hover:border-brand-600/50 transition-colors"
    >
      <div className="h-10 w-10 rounded-lg bg-surface-2 flex items-center justify-center group-hover:bg-brand-600/20 transition-colors">
        <Icon className="h-5 w-5 text-gray-400 group-hover:text-brand-400 transition-colors" />
      </div>
      <div>
        <h3 className="font-semibold text-white">{title}</h3>
        <p className="text-sm text-gray-500 mt-1">{desc}</p>
      </div>
    </Link>
  );
}
