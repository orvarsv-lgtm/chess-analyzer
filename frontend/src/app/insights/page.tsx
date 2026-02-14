"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import Link from "next/link";
import {
  BarChart3,
  TrendingUp,
  TrendingDown,
  Minus,
  AlertTriangle,
  Target,
  Zap,
  Clock,
  Flame,
  BookOpen,
  ChevronDown,
  ChevronRight,
  Dumbbell,
  ArrowRight,
  Shield,
  Swords,
  GraduationCap,
  ThumbsUp,
  ThumbsDown,
  Activity,
  Crown,
  User,
  Sparkles,
} from "lucide-react";
import {
  Radar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";
import {
  insightsAPI,
  patternsAPI,
  type InsightsOverview,
  type PhaseBreakdown,
  type Weakness,
  type TimeAnalysis,
  type StreakData,
  type OpeningStat,
  type AdvancedAnalytics,
  type PiecePerformance,
  type RecurringPattern,
  type SkillProfile,
  type ProgressDataPoint,
  type ChessIdentity,
} from "@/lib/api";
import {
  Card,
  CardContent,
  Badge,
  Button,
  Spinner,
  EmptyState,
} from "@/components/ui";
import { cplToAccuracy, accuracyColor, formatAccuracy } from "@/lib/utils";

export default function InsightsPage() {
  const { data: session } = useSession();

  const [overview, setOverview] = useState<InsightsOverview | null>(null);
  const [phases, setPhases] = useState<PhaseBreakdown | null>(null);
  const [weaknesses, setWeaknesses] = useState<Weakness[]>([]);
  const [timeData, setTimeData] = useState<TimeAnalysis | null>(null);
  const [streakData, setStreakData] = useState<StreakData | null>(null);
  const [openings, setOpenings] = useState<OpeningStat[]>([]);
  const [loading, setLoading] = useState(true);
  const [advanced, setAdvanced] = useState<AdvancedAnalytics | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [advancedLoading, setAdvancedLoading] = useState(false);
  const [advancedFilter, setAdvancedFilter] = useState<string>("all");
  const [recurringPatterns, setRecurringPatterns] = useState<RecurringPattern[]>([]);
  const [skillProfile, setSkillProfile] = useState<SkillProfile | null>(null);
  const [progressData, setProgressData] = useState<ProgressDataPoint[]>([]);
  const [identity, setIdentity] = useState<ChessIdentity | null>(null);

  function weaknessTrainUrl(area: string): string {
    const a = area.toLowerCase();
    if (a === "opening") return "/train?phase=opening";
    if (a === "middlegame") return "/train?phase=middlegame";
    if (a === "endgame") return "/train?phase=endgame";
    if (a.includes("converting") || a.includes("advantage")) return "/train?mode=advantage";
    if (a.includes("blunder")) return "/train?mode=warmup";
    if (a.includes("time")) return "/train?mode=timed";
    return "/train?mode=warmup";
  }

  useEffect(() => {
    if (!session) return;

    async function load() {
      setLoading(true);
      try {
        const [ov, ph, wk, tm, st, op, pat, sp, prog, id] = await Promise.all([
          insightsAPI.overview(),
          insightsAPI.phaseBreakdown(),
          insightsAPI.weaknesses(),
          insightsAPI.timeAnalysis().catch(() => null),
          insightsAPI.streaks().catch(() => null),
          insightsAPI.openings().catch(() => []),
          patternsAPI.recurring().catch(() => ({ patterns: [] })),
          insightsAPI.skillProfile().catch(() => null),
          insightsAPI.progress(6).catch(() => null),
          insightsAPI.chessIdentity().catch(() => null),
        ]);
        setOverview(ov);
        setPhases(ph);
        setWeaknesses(wk.weaknesses ?? []);
        setTimeData(tm);
        setStreakData(st);
        setOpenings(op);
        setRecurringPatterns(pat.patterns ?? []);
        if (sp) setSkillProfile(sp);
        if (prog) setProgressData(prog.data ?? []);
        if (id) setIdentity(id);
      } catch {
        // API may not be connected yet
      } finally {
        setLoading(false);
      }
    }

    load();
  }, [session]);

  async function loadAdvanced(filter?: string) {
    if (advancedLoading) return;
    setAdvancedLoading(true);
    try {
      const data = await insightsAPI.advancedAnalytics(filter || advancedFilter);
      setAdvanced(data);
    } catch {
      // not available
    } finally {
      setAdvancedLoading(false);
    }
  }

  function handleShowAdvanced() {
    setShowAdvanced(true);
    loadAdvanced();
  }

  if (!session) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-gray-500">Sign in to view your insights.</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Spinner className="h-8 w-8 text-brand-500" />
      </div>
    );
  }

  const hasData = overview && overview.total_games > 0;
  const accuracy = cplToAccuracy(overview?.overall_cpl);
  const recentAccuracy = cplToAccuracy(overview?.recent_cpl);

  return (
    <div className="max-w-4xl mx-auto px-6 py-8 space-y-8 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold">Insights</h1>
        <p className="text-gray-500 mt-1">
          Your performance overview and where to improve.
        </p>
      </div>

      {!hasData ? (
        <Card>
          <EmptyState
            icon={<BarChart3 className="h-12 w-12" />}
            title="No data yet"
            description="Import and analyze some games to see your insights."
          />
        </Card>
      ) : (
        <>
          {/* ─── Chess Identity Card ─── */}
          {identity?.has_data && identity.persona && (
            <>
              <IdentityCard identity={identity} />
              <Link
                href="/insights/report"
                className="w-full flex items-center justify-center gap-3 px-6 py-4 rounded-xl border-2 border-dashed transition-all hover:border-solid group"
                style={{
                  borderColor: `${identity.persona.color}40`,
                  background: `linear-gradient(135deg, ${identity.persona.color}08 0%, transparent 60%)`,
                }}
              >
                <Sparkles className="h-5 w-5 transition-transform group-hover:scale-110" style={{ color: identity.persona.color }} />
                <span className="text-sm font-semibold" style={{ color: identity.persona.color }}>
                  View Your AI Coach Report
                </span>
                <span className="text-xs text-gray-500 ml-1">— Personalized training plan &amp; actionable advice</span>
              </Link>
            </>
          )}

          {/* ─── Above the fold: Accuracy hero + 3 insight cards ─── */}
          <div className="text-center py-4">
            <p className="text-sm text-gray-500 uppercase tracking-wider mb-1">Overall Accuracy</p>
            <p className={`text-5xl font-bold ${accuracyColor(accuracy)}`}>
              {accuracy !== null ? `${accuracy}%` : "—"}
            </p>
            {overview!.trend && (
              <div className={`inline-flex items-center gap-1.5 mt-2 text-xs font-medium px-3 py-1 rounded-full ${
                overview!.trend === "improving"
                  ? "bg-green-900/20 text-green-400"
                  : overview!.trend === "declining"
                  ? "bg-red-900/20 text-red-400"
                  : "bg-surface-2 text-gray-400"
              }`}>
                {overview!.trend === "improving" ? <TrendingUp className="h-3 w-3" /> : overview!.trend === "declining" ? <TrendingDown className="h-3 w-3" /> : <Minus className="h-3 w-3" />}
                {overview!.trend === "improving"
                  ? "Improving"
                  : overview!.trend === "declining"
                  ? "Declining"
                  : "Stable"}
                {recentAccuracy !== null && <span className="opacity-80 ml-1">({recentAccuracy}% recent)</span>}
              </div>
            )}
          </div>

          {/* 3 insight cards — max above the fold */}
          <div className="grid sm:grid-cols-3 gap-4">
            <InsightCard
              icon={<Target className="h-5 w-5 text-brand-400" />}
              label="Games"
              value={String(overview!.total_games)}
              sub={`${overview!.win_rate ?? 0}% win rate`}
            />
            <InsightCard
              icon={<Zap className="h-5 w-5 text-yellow-400" />}
              label="Blunders"
              value={overview!.blunder_rate !== null ? `${overview!.blunder_rate}` : "—"}
              sub="per 100 moves"
            />
            {streakData && streakData.current_streak > 0 ? (
              <InsightCard
                icon={<Flame className="h-5 w-5 text-orange-400" />}
                label="Streak"
                value={String(streakData.current_streak)}
                sub={`${streakData.current_streak_type} streak`}
              />
            ) : (
              <InsightCard
                icon={<Flame className="h-5 w-5 text-gray-600" />}
                label="Streak"
                value="0"
                sub="No active streak"
              />
            )}
          </div>

          {/* ─── Skill Radar Chart ─── */}
          {skillProfile?.has_data && skillProfile.axes && (
            <Card>
              <div className="p-6">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2">
                    <Target className="h-5 w-5 text-brand-400" />
                    <h3 className="font-semibold">Skill Profile</h3>
                  </div>
                  <span className="text-sm text-gray-500">
                    Overall: <span className="text-brand-400 font-bold">{skillProfile.overall_score}</span>/100
                  </span>
                </div>
                <div className="h-80">
                  <ResponsiveContainer width="100%" height="100%">
                    <RadarChart data={skillProfile.axes} cx="50%" cy="50%" outerRadius="75%">
                      <PolarGrid stroke="#333" />
                      <PolarAngleAxis
                        dataKey="axis"
                        tick={{ fill: "#9ca3af", fontSize: 12, fontWeight: 500 }}
                      />
                      <PolarRadiusAxis
                        angle={30}
                        domain={[0, 100]}
                        tick={{ fill: "#666", fontSize: 10 }}
                        axisLine={false}
                      />
                      <Radar
                        name="Skill"
                        dataKey="score"
                        stroke="#16a34a"
                        fill="#16a34a"
                        fillOpacity={0.2}
                        strokeWidth={2}
                        dot={{ r: 4, fill: "#16a34a" }}
                      />
                    </RadarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </Card>
          )}

          {/* ─── Progress Charts ─── */}
          {progressData.length >= 2 && (
            <Card>
              <div className="p-6">
                <div className="flex items-center gap-2 mb-6">
                  <Activity className="h-5 w-5 text-brand-400" />
                  <h3 className="font-semibold">Progress Over Time</h3>
                </div>

                {/* Accuracy trend */}
                <div className="mb-6">
                  <p className="text-xs text-gray-500 uppercase tracking-wider mb-3">Accuracy</p>
                  <div className="h-48">
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={progressData}>
                        <defs>
                          <linearGradient id="accGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#16a34a" stopOpacity={0.3} />
                            <stop offset="95%" stopColor="#16a34a" stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                        <XAxis
                          dataKey="period"
                          tick={{ fill: "#9ca3af", fontSize: 11 }}
                          axisLine={{ stroke: "#444" }}
                          tickLine={false}
                        />
                        <YAxis
                          domain={[0, 100]}
                          tick={{ fill: "#9ca3af", fontSize: 11 }}
                          axisLine={false}
                          tickLine={false}
                          width={35}
                        />
                        <Tooltip
                          contentStyle={{
                            backgroundColor: "#1a1a1a",
                            border: "1px solid #444",
                            borderRadius: "8px",
                            fontSize: 12,
                          }}
                          labelStyle={{ color: "#9ca3af" }}
                        />
                        <Area
                          type="monotone"
                          dataKey="accuracy"
                          stroke="#16a34a"
                          fill="url(#accGrad)"
                          strokeWidth={2}
                          dot={{ r: 3, fill: "#16a34a" }}
                          name="Accuracy %"
                          connectNulls
                        />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                {/* Blunder rate trend */}
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wider mb-3">Blunder Rate (per 100 moves)</p>
                  <div className="h-48">
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={progressData}>
                        <defs>
                          <linearGradient id="blunderGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#ef4444" stopOpacity={0.3} />
                            <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                        <XAxis
                          dataKey="period"
                          tick={{ fill: "#9ca3af", fontSize: 11 }}
                          axisLine={{ stroke: "#444" }}
                          tickLine={false}
                        />
                        <YAxis
                          tick={{ fill: "#9ca3af", fontSize: 11 }}
                          axisLine={false}
                          tickLine={false}
                          width={35}
                        />
                        <Tooltip
                          contentStyle={{
                            backgroundColor: "#1a1a1a",
                            border: "1px solid #444",
                            borderRadius: "8px",
                            fontSize: 12,
                          }}
                          labelStyle={{ color: "#9ca3af" }}
                        />
                        <Area
                          type="monotone"
                          dataKey="blunder_rate"
                          stroke="#ef4444"
                          fill="url(#blunderGrad)"
                          strokeWidth={2}
                          dot={{ r: 3, fill: "#ef4444" }}
                          name="Blunders/100"
                          connectNulls
                        />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              </div>
            </Card>
          )}

          {/* ─── Collapsible sections below the fold ─── */}

          {/* Weaknesses */}
          <CollapsibleInsight title="Weaknesses" icon={<AlertTriangle className="h-4 w-4 text-red-400" />} defaultOpen={true}>
            {weaknesses.length === 0 ? (
              <p className="text-gray-500 text-sm">Not enough data to determine weaknesses yet.</p>
            ) : (
              <div className="space-y-3">
                {weaknesses.slice(0, 3).map((w, i) => (
                  <div
                    key={i}
                    className={`flex items-start gap-3 p-4 rounded-lg border ${
                      w.severity === "high"
                        ? "bg-red-900/10 border-red-800/30"
                        : w.severity === "medium"
                        ? "bg-yellow-900/10 border-yellow-800/30"
                        : "bg-surface-2 border-surface-3"
                    }`}
                  >
                    <AlertTriangle className={`h-5 w-5 mt-0.5 flex-shrink-0 ${
                      w.severity === "high" ? "text-red-400" : w.severity === "medium" ? "text-yellow-400" : "text-gray-400"
                    }`} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-sm">{w.area}</span>
                        <Badge variant={w.severity === "high" ? "danger" : w.severity === "medium" ? "warning" : "default"}>
                          {w.severity}
                        </Badge>
                      </div>
                      <p className="text-sm text-gray-400 mt-1">{w.message}</p>
                      <Link href={weaknessTrainUrl(w.area)} className="text-sm text-brand-400 mt-1.5 flex items-center gap-1 hover:gap-2 transition-all">
                        <Dumbbell className="h-3 w-3" /> Train this <ArrowRight className="h-3 w-3" />
                      </Link>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CollapsibleInsight>

          {/* Recurring Patterns (Cross-Game Detection) */}
          {recurringPatterns.length > 0 && (
            <CollapsibleInsight title="Recurring Patterns" icon={<Sparkles className="h-4 w-4 text-purple-400" />} defaultOpen={false}>
              <div className="space-y-3">
                {recurringPatterns.slice(0, 5).map((p, i) => (
                  <div
                    key={i}
                    className={`p-4 rounded-lg border ${
                      p.severity === "high"
                        ? "bg-red-900/10 border-red-800/30"
                        : p.severity === "medium"
                        ? "bg-yellow-900/10 border-yellow-800/30"
                        : "bg-surface-2 border-surface-3"
                    }`}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <Badge variant={p.severity === "high" ? "danger" : p.severity === "medium" ? "warning" : "default"}>
                        {p.pattern_type.replace("_", " ")}
                      </Badge>
                      <span className="text-xs text-gray-600">
                        {p.occurrences} occurrences
                      </span>
                    </div>
                    <p className="text-sm text-gray-300">{p.description}</p>
                    <p className="text-xs text-brand-400 mt-2 flex items-center gap-1">
                      <GraduationCap className="h-3 w-3" />
                      {p.recommendation}
                    </p>
                  </div>
                ))}
              </div>
            </CollapsibleInsight>
          )}

          {/* Phase Accuracy */}
          <CollapsibleInsight title="Phase Accuracy" icon={<BarChart3 className="h-4 w-4 text-brand-400" />}>
            <div className="grid grid-cols-3 gap-6">
              <PhaseColumn label="Opening" cpl={phases?.opening ?? null} />
              <PhaseColumn label="Middlegame" cpl={phases?.middlegame ?? null} />
              <PhaseColumn label="Endgame" cpl={phases?.endgame ?? null} />
            </div>
          </CollapsibleInsight>

          {/* Openings (merged from openings page) */}
          {openings.length > 0 && (
            <CollapsibleInsight title="Opening Repertoire" icon={<BookOpen className="h-4 w-4 text-green-400" />}>
              <div className="space-y-2">
                {[...openings]
                  .sort((a, b) => b.games_played - a.games_played)
                  .slice(0, 8)
                  .map((o, i) => {
                    const acc = cplToAccuracy(o.average_cpl);
                    const winColor = o.win_rate >= 60 ? "text-green-400" : o.win_rate >= 45 ? "text-yellow-400" : "text-red-400";
                    return (
                      <div
                        key={`${o.opening_name}-${o.color}-${i}`}
                        className="flex items-center justify-between px-4 py-2.5 bg-surface-2/50 rounded-lg text-sm"
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          <span className={`inline-flex h-6 w-6 rounded items-center justify-center text-xs font-bold ${
                            o.color === "white"
                              ? "bg-white text-gray-900"
                              : "bg-gray-800 text-white border border-surface-3"
                          }`}>
                            {o.color === "white" ? "♔" : "♚"}
                          </span>
                          <span className="font-medium truncate">{o.opening_name}</span>
                          <span className="text-xs text-gray-600">{o.eco_code}</span>
                        </div>
                        <div className="flex items-center gap-4 text-gray-400 flex-shrink-0">
                          <span>{o.games_played}g</span>
                          <span className={winColor}>{o.win_rate}%</span>
                          <span className={accuracyColor(acc)}>{acc !== null ? `${acc}%` : "—"}</span>
                        </div>
                      </div>
                    );
                  })}
              </div>
            </CollapsibleInsight>
          )}

          {/* Time Management */}
          {timeData && (
            <CollapsibleInsight title="Time Management" icon={<Clock className="h-4 w-4 text-brand-400" />}>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-4">
                <div className="p-3 bg-surface-2 rounded-lg">
                  <p className="text-xs text-gray-500 uppercase">Avg Move Time</p>
                  <p className="text-xl font-bold mt-1">
                    {timeData.avg_move_time ? `${timeData.avg_move_time}s` : "—"}
                  </p>
                </div>
                <div className="p-3 bg-surface-2 rounded-lg">
                  <p className="text-xs text-gray-500 uppercase">Time Pressure Blunders</p>
                  <p className="text-xl font-bold mt-1 text-red-400">{timeData.time_pressure_blunders ?? 0}</p>
                  <p className="text-xs text-gray-500">in {timeData.time_pressure_moves ?? 0} moves</p>
                </div>
                <div className="p-3 bg-surface-2 rounded-lg">
                  <p className="text-xs text-gray-500 uppercase">Normal Blunders</p>
                  <p className="text-xl font-bold mt-1 text-orange-400">{timeData.normal_blunders ?? 0}</p>
                  <p className="text-xs text-gray-500">in {timeData.normal_moves ?? 0} moves</p>
                </div>
              </div>
              {timeData.time_controls.length > 0 && (
                <div className="space-y-2">
                  {timeData.time_controls.slice(0, 4).map((tc) => (
                    <div key={tc.time_control} className="flex items-center justify-between px-3 py-2 bg-surface-2/50 rounded-lg text-sm">
                      <span className="font-medium">{tc.time_control}</span>
                      <div className="flex items-center gap-4 text-gray-400">
                        <span>{tc.games}g</span>
                        <span className="text-green-400">{tc.win_rate}%</span>
                        <span className={accuracyColor(cplToAccuracy(tc.avg_cpl))}>
                          {formatAccuracy(tc.avg_cpl)}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CollapsibleInsight>
          )}

          {/* ─── See Advanced Analytics ─── */}
          {!showAdvanced ? (
            <button
              onClick={handleShowAdvanced}
              className="w-full flex items-center justify-center gap-2 py-4 px-6 rounded-xl border border-dashed border-surface-3 hover:border-brand-500/50 hover:bg-surface-2/50 transition-all text-gray-400 hover:text-brand-400 group"
            >
              <Sparkles className="h-4 w-4" />
              <span className="font-medium">See Advanced Analytics</span>
              <ChevronRight className="h-4 w-4 group-hover:translate-x-0.5 transition-transform" />
            </button>
          ) : (
            <div className="space-y-6 animate-fade-in">
              <div className="flex items-center justify-between pt-2">
                <div className="flex items-center gap-2">
                  <Sparkles className="h-5 w-5 text-brand-400" />
                  <h2 className="text-lg font-bold">Advanced Analytics</h2>
                </div>
              </div>

              {/* Time Control Filter Tabs */}
              <div className="flex gap-1.5 p-1 bg-surface-2 rounded-lg w-fit">
                {(["all", "bullet", "blitz", "rapid", "classical"] as const).map((tc) => {
                  const icons: Record<string, string> = { all: "🎯", bullet: "⚡", blitz: "🔥", rapid: "⏱️", classical: "🏛️" };
                  const isActive = advancedFilter === tc;
                  return (
                    <button
                      key={tc}
                      onClick={() => {
                        setAdvancedFilter(tc);
                        setAdvanced(null);
                        loadAdvanced(tc);
                      }}
                      className={`px-3 py-1.5 rounded-md text-sm font-medium transition-all ${
                        isActive
                          ? "bg-brand-500/20 text-brand-400 shadow-sm"
                          : "text-gray-400 hover:text-gray-300 hover:bg-surface-3/50"
                      }`}
                    >
                      <span className="mr-1">{icons[tc]}</span>
                      {tc.charAt(0).toUpperCase() + tc.slice(1)}
                    </button>
                  );
                })}
              </div>

              {advancedLoading && (
                <Card className="py-12 flex items-center justify-center">
                  <Spinner className="h-6 w-6 text-brand-500" />
                </Card>
              )}

              {advanced && !advanced.has_data && (
                <Card>
                  <div className="p-6 text-center text-gray-500">
                    <p>{advanced.message || "Not enough data yet."}</p>
                  </div>
                </Card>
              )}

              {advanced && advanced.has_data && (
                <>
                  {/* Player Style */}
                  {advanced.primary_style && (
                    <Card>
                      <div className="p-6">
                        <h3 className="font-semibold text-sm text-gray-500 uppercase tracking-wider mb-4">Your Playing Style</h3>
                        <div className="flex items-start gap-4 mb-4">
                          <span className="text-4xl">{advanced.primary_style.icon}</span>
                          <div>
                            <p className="text-xl font-bold text-brand-400">{advanced.primary_style.trait}</p>
                            <p className="text-sm text-gray-400 mt-1">{advanced.primary_style.description}</p>
                          </div>
                        </div>
                        {advanced.secondary_styles && advanced.secondary_styles.length > 0 && (
                          <div className="flex flex-wrap gap-2 mt-4 pt-4 border-t border-surface-3">
                            {advanced.secondary_styles.map((s, i) => (
                              <span
                                key={i}
                                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-surface-2 text-sm"
                                title={s.description}
                              >
                                <span>{s.icon}</span>
                                <span className="font-medium">{s.trait}</span>
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    </Card>
                  )}

                  {/* Comeback & Collapse */}
                  <div className="grid sm:grid-cols-2 gap-4">
                    <Card className="p-5">
                      <div className="flex items-start justify-between">
                        <div>
                          <p className="text-xs text-gray-500 uppercase tracking-wider">Comeback Wins</p>
                          <p className="text-3xl font-bold text-green-400 mt-1">{advanced.comeback_wins ?? 0}</p>
                          <p className="text-xs text-gray-500 mt-1">Won from losing positions (−2+ pawns)</p>
                        </div>
                        <ThumbsUp className="h-5 w-5 text-green-400/60" />
                      </div>
                    </Card>
                    <Card className="p-5">
                      <div className="flex items-start justify-between">
                        <div>
                          <p className="text-xs text-gray-500 uppercase tracking-wider">Collapses</p>
                          <p className="text-3xl font-bold text-red-400 mt-1">{advanced.collapses ?? 0}</p>
                          <p className="text-xs text-gray-500 mt-1">Lost from winning positions (+2 pawns)</p>
                        </div>
                        <ThumbsDown className="h-5 w-5 text-red-400/60" />
                      </div>
                    </Card>
                  </div>

                  {/* Best & Worst Openings */}
                  {((advanced.best_openings && advanced.best_openings.length > 0) ||
                    (advanced.worst_openings && advanced.worst_openings.length > 0)) && (
                    <div className="grid sm:grid-cols-2 gap-4">
                      {advanced.best_openings && advanced.best_openings.length > 0 && (
                        <Card>
                          <div className="p-5">
                            <div className="flex items-center gap-2 mb-3">
                              <BookOpen className="h-4 w-4 text-green-400" />
                              <h3 className="font-semibold text-sm">Best Openings</h3>
                            </div>
                            <div className="space-y-2">
                              {advanced.best_openings.map((o, i) => (
                                <div key={i} className="flex items-center justify-between px-3 py-2 bg-green-900/10 border border-green-800/20 rounded-lg text-sm">
                                  <span className="font-medium truncate flex-1 mr-2">{o.name}</span>
                                  <div className="flex items-center gap-3 text-xs flex-shrink-0">
                                    <span className="text-gray-400">{o.games}g</span>
                                    <span className="text-green-400">{o.win_rate}%</span>
                                    <span className={accuracyColor(cplToAccuracy(o.avg_cpl))}>
                                      {cplToAccuracy(o.avg_cpl) !== null ? `${cplToAccuracy(o.avg_cpl)}%` : "—"}
                                    </span>
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        </Card>
                      )}
                      {advanced.worst_openings && advanced.worst_openings.length > 0 && (
                        <Card>
                          <div className="p-5">
                            <div className="flex items-center gap-2 mb-3">
                              <BookOpen className="h-4 w-4 text-red-400" />
                              <h3 className="font-semibold text-sm">Worst Openings</h3>
                            </div>
                            <div className="space-y-2">
                              {advanced.worst_openings.map((o, i) => (
                                <div key={i} className="flex items-center justify-between px-3 py-2 bg-red-900/10 border border-red-800/20 rounded-lg text-sm">
                                  <span className="font-medium truncate flex-1 mr-2">{o.name}</span>
                                  <div className="flex items-center gap-3 text-xs flex-shrink-0">
                                    <span className="text-gray-400">{o.games}g</span>
                                    <span className="text-red-400">{o.win_rate}%</span>
                                    <span className={accuracyColor(cplToAccuracy(o.avg_cpl))}>
                                      {cplToAccuracy(o.avg_cpl) !== null ? `${cplToAccuracy(o.avg_cpl)}%` : "—"}
                                    </span>
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        </Card>
                      )}
                    </div>
                  )}

                  {/* Piece Performance */}
                  {advanced.all_pieces && advanced.all_pieces.length > 0 && (
                    <Card>
                      <div className="p-5">
                        <div className="flex items-center gap-2 mb-4">
                          <span className="text-lg">♟</span>
                          <h3 className="font-semibold text-sm">Piece Performance</h3>
                        </div>
                        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-3">
                          {advanced.all_pieces.map((p) => {
                            const acc = cplToAccuracy(p.avg_cpl);
                            return (
                              <div
                                key={p.piece}
                                className="flex flex-col items-center p-3 bg-surface-2 rounded-lg"
                              >
                                <span className="text-3xl mb-1">{p.icon}</span>
                                <span className="text-xs font-medium text-gray-400">{p.name}</span>
                                <span className={`text-lg font-bold mt-1 ${accuracyColor(acc)}`}>
                                  {acc !== null ? `${acc}%` : "—"}
                                </span>
                                <div className="flex gap-2 mt-1 text-[10px] text-gray-500">
                                  <span>{p.total_moves} moves</span>
                                </div>
                                <div className="flex gap-2 mt-0.5 text-[10px]">
                                  <span className="text-green-400">⭐ {p.best_rate}%</span>
                                  <span className="text-red-400">💥 {p.blunder_rate}%</span>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    </Card>
                  )}

                  {/* Strengths & Weaknesses */}
                  <div className="grid sm:grid-cols-2 gap-4">
                    <Card>
                      <div className="p-5">
                        <div className="flex items-center gap-2 mb-3">
                          <Shield className="h-4 w-4 text-green-400" />
                          <h3 className="font-semibold text-sm">Strengths</h3>
                        </div>
                        <div className="space-y-2.5">
                          {(advanced.strengths ?? []).map((s, i) => (
                            <div key={i} className="p-3 bg-green-900/10 border border-green-800/20 rounded-lg">
                              <p className="text-sm font-medium text-green-400">{s.area}</p>
                              <p className="text-xs text-gray-400 mt-0.5">{s.detail}</p>
                            </div>
                          ))}
                          {(!advanced.strengths || advanced.strengths.length === 0) && (
                            <p className="text-sm text-gray-500">Keep analyzing games to discover your strengths.</p>
                          )}
                        </div>
                      </div>
                    </Card>
                    <Card>
                      <div className="p-5">
                        <div className="flex items-center gap-2 mb-3">
                          <Swords className="h-4 w-4 text-red-400" />
                          <h3 className="font-semibold text-sm">Weaknesses</h3>
                        </div>
                        <div className="space-y-2.5">
                          {(advanced.weaknesses ?? []).map((w, i) => (
                            <div key={i} className="p-3 bg-red-900/10 border border-red-800/20 rounded-lg">
                              <p className="text-sm font-medium text-red-400">{w.area}</p>
                              <p className="text-xs text-gray-400 mt-0.5">{w.detail}</p>
                            </div>
                          ))}
                          {(!advanced.weaknesses || advanced.weaknesses.length === 0) && (
                            <p className="text-sm text-gray-500">No major weaknesses detected — great work!</p>
                          )}
                        </div>
                      </div>
                    </Card>
                  </div>

                  {/* Study Recommendations */}
                  {advanced.recommendations && advanced.recommendations.length > 0 && (
                    <Card>
                      <div className="p-5">
                        <div className="flex items-center gap-2 mb-4">
                          <GraduationCap className="h-4 w-4 text-brand-400" />
                          <h3 className="font-semibold text-sm">Study Recommendations</h3>
                        </div>
                        <div className="space-y-3">
                          {advanced.recommendations.map((r, i) => (
                            <div key={i} className="flex items-start gap-3">
                              <span className={`mt-0.5 h-2 w-2 rounded-full flex-shrink-0 ${
                                r.priority === "high" ? "bg-red-400" : r.priority === "medium" ? "bg-yellow-400" : "bg-green-400"
                              }`} />
                              <div>
                                <p className="text-sm font-medium">{r.category}</p>
                                <p className="text-xs text-gray-400 mt-0.5">{r.message}</p>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    </Card>
                  )}

                  {/* Raw Stats Footer */}
                  {advanced.stats && (
                    <Card>
                      <div className="p-5">
                        <h3 className="font-semibold text-sm text-gray-500 uppercase tracking-wider mb-3">Key Numbers</h3>
                        <div className="grid grid-cols-3 sm:grid-cols-5 gap-4 text-center">
                          <div>
                            <p className="text-lg font-bold">{advanced.stats.avg_cpl}</p>
                            <p className="text-xs text-gray-500">Avg CPL</p>
                          </div>
                          <div>
                            <p className="text-lg font-bold">{advanced.stats.best_move_rate}%</p>
                            <p className="text-xs text-gray-500">Best Moves</p>
                          </div>
                          <div>
                            <p className="text-lg font-bold">{advanced.stats.blunder_rate}</p>
                            <p className="text-xs text-gray-500">Blunders/100</p>
                          </div>
                          <div>
                            <p className="text-lg font-bold">{advanced.stats.win_rate}%</p>
                            <p className="text-xs text-gray-500">Win Rate</p>
                          </div>
                          <div>
                            <p className="text-lg font-bold">{advanced.stats.upsets}</p>
                            <p className="text-xs text-gray-500">Giant Kills</p>
                          </div>
                        </div>
                      </div>
                    </Card>
                  )}
                </>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ─── Insight Card ───────────────────────────────────────

function InsightCard({
  icon,
  label,
  value,
  sub,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  sub: string;
}) {
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs text-gray-500 uppercase tracking-wider">{label}</p>
          <p className="text-2xl font-bold mt-1">{value}</p>
          <p className="text-xs text-gray-500 mt-0.5">{sub}</p>
        </div>
        <div className="text-gray-500">{icon}</div>
      </div>
    </Card>
  );
}

// ─── Collapsible Insight Section ────────────────────────

function CollapsibleInsight({
  title,
  icon,
  defaultOpen = false,
  children,
}: {
  title: string;
  icon?: React.ReactNode;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  return (
    <Card>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between px-5 py-4 text-left"
      >
        <span className="font-semibold flex items-center gap-2">
          {icon}
          {title}
        </span>
        <ChevronDown className={`h-4 w-4 text-gray-500 transition-transform ${isOpen ? "rotate-180" : ""}`} />
      </button>
      {isOpen && (
        <div className="px-5 pb-5">
          {children}
        </div>
      )}
    </Card>
  );
}

// ─── Chess Identity Card ────────────────────────────────

function IdentityCard({ identity }: { identity: ChessIdentity }) {
  const persona = identity.persona!;

  return (
    <Card className="overflow-hidden">
      {/* ═══ Hero Banner ═══ */}
      <div
        className="relative p-6 pb-5"
        style={{
          background: `linear-gradient(135deg, ${persona.color}18 0%, ${persona.color}06 50%, transparent 80%)`,
        }}
      >
        <div className="flex items-start gap-4">
          <div
            className="flex items-center justify-center h-20 w-20 rounded-2xl text-5xl flex-shrink-0 shadow-lg"
            style={{ backgroundColor: `${persona.color}20`, boxShadow: `0 4px 20px ${persona.color}15` }}
          >
            {persona.emoji}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-0.5">
              <Crown className="h-4 w-4" style={{ color: persona.color }} />
              <span className="text-xs font-semibold uppercase tracking-wider text-gray-500">
                Your Chess Identity
              </span>
            </div>
            <h2 className="text-3xl font-bold tracking-tight" style={{ color: persona.color }}>
              {persona.name}
            </h2>
            <p className="text-base text-gray-400 italic mt-1">
              &ldquo;{persona.tagline}&rdquo;
            </p>
            <div className="flex items-center gap-3 mt-2">
              <p className="text-sm text-gray-500 flex items-center gap-1.5">
                <User className="h-3.5 w-3.5" />
                Plays like <span className="font-semibold text-gray-300">{persona.gm_comparison}</span>
              </p>
              {identity.secondary_persona && (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-surface-2/80 text-xs font-medium border border-surface-3">
                  <span>{identity.secondary_persona.emoji}</span>
                  Also: {identity.secondary_persona.name}
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="px-6 pb-7 space-y-6">
        {/* ═══ What This Means (persona description) ═══ */}
        <div className="pt-2">
          <SectionHeader icon="📋" title="What This Means" color={persona.color} />
          <p className="text-sm text-gray-300 leading-relaxed mt-3">
            {persona.description}
          </p>
        </div>

        {/* ═══ Why You — personalized match reasons ═══ */}
        {identity.why_you && identity.why_you.length > 0 && (
          <div>
            <SectionHeader icon="🔍" title="Why You're The Phoenix" overrideTitle={`Why You're ${persona.name}`} color={persona.color} />
            <div className="mt-3 space-y-2.5">
              {identity.why_you.map((reason, i) => (
                <div key={i} className="flex items-start gap-3 text-sm">
                  <span
                    className="mt-1.5 h-2 w-2 rounded-full flex-shrink-0"
                    style={{ backgroundColor: persona.color }}
                  />
                  <p className="text-gray-300 leading-relaxed">{reason}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ═══ Behavioral Tendencies ═══ */}
        {identity.tendencies && identity.tendencies.length > 0 && (
          <div>
            <SectionHeader icon="🧬" title="Your Tendencies" color={persona.color} />
            <div className="mt-3 grid sm:grid-cols-2 gap-3">
              {identity.tendencies.map((t, i) => (
                <div
                  key={i}
                  className="flex items-start gap-3 p-3.5 bg-surface-2/50 rounded-lg border border-surface-3/50"
                >
                  <span className="text-xl flex-shrink-0">{t.icon}</span>
                  <div>
                    <p className="text-sm font-semibold">{t.label}</p>
                    <p className="text-xs text-gray-400 mt-0.5 leading-relaxed">{t.description}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ═══ Signature Stats ═══ */}
        {identity.signature_stats && identity.signature_stats.length > 0 && (
          <div>
            <SectionHeader icon="📊" title="Signature Stats" color={persona.color} />
            <div className="mt-3 grid grid-cols-2 sm:grid-cols-3 gap-3">
              {identity.signature_stats.map((stat, i) => (
                <div
                  key={i}
                  className="p-3.5 bg-surface-2/40 rounded-lg border border-surface-3/30"
                >
                  <p className="text-xs text-gray-500 font-medium">{stat.label}</p>
                  <p className="text-xl font-bold mt-1">{stat.value}</p>
                  <p className="text-xs text-gray-500 mt-1">{stat.detail}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ═══ Phase Breakdown ═══ */}
        {identity.phase_breakdown && identity.phase_breakdown.length > 0 && (
          <div>
            <SectionHeader icon="🎯" title="Phase Breakdown" color={persona.color} />
            <div className="mt-3 space-y-3">
              {identity.phase_breakdown.map((phase, i) => (
                <div
                  key={i}
                  className={`p-4 rounded-lg border ${
                    phase.tag === "strongest"
                      ? "bg-green-900/8 border-green-800/20"
                      : phase.tag === "weakest"
                      ? "bg-red-900/8 border-red-800/20"
                      : "bg-surface-2/30 border-surface-3/30"
                  }`}
                >
                  <div className="flex items-center justify-between mb-1.5">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold">{phase.phase}</span>
                      <span className={`text-[10px] uppercase tracking-wider font-bold px-2 py-0.5 rounded-full ${
                        phase.tag === "strongest"
                          ? "bg-green-900/30 text-green-400"
                          : phase.tag === "weakest"
                          ? "bg-red-900/30 text-red-400"
                          : "bg-surface-3/50 text-gray-500"
                      }`}>
                        {phase.tag}
                      </span>
                    </div>
                    <div className="flex items-center gap-3 text-sm">
                      <span className="text-gray-500">{phase.cpl} CPL</span>
                      <span className={`font-bold ${
                        phase.score >= 75 ? "text-green-400" : phase.score >= 50 ? "text-yellow-400" : "text-red-400"
                      }`}>
                        {phase.score}/100
                      </span>
                    </div>
                  </div>
                  {/* Score bar */}
                  <div className="h-1.5 bg-surface-3/50 rounded-full mb-2">
                    <div
                      className={`h-full rounded-full transition-all duration-700 ${
                        phase.tag === "strongest" ? "bg-green-500" : phase.tag === "weakest" ? "bg-red-500" : "bg-gray-500"
                      }`}
                      style={{ width: `${phase.score}%` }}
                    />
                  </div>
                  <p className="text-xs text-gray-400 leading-relaxed">{phase.commentary}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ═══ Skill Shape Radar ═══ */}
        {identity.skill_axes && (
          <div>
            <div className="flex items-center justify-between">
              <SectionHeader icon="🕸️" title="Skill Shape" color={persona.color} />
              <span className="text-sm text-gray-500">
                Overall: <span className="text-lg font-bold" style={{ color: persona.color }}>{identity.overall_score}</span>/100
              </span>
            </div>
            <div className="h-64 mt-2">
              <ResponsiveContainer width="100%" height="100%">
                <RadarChart data={identity.skill_axes} cx="50%" cy="50%" outerRadius="72%">
                  <PolarGrid stroke="#333" />
                  <PolarAngleAxis
                    dataKey="axis"
                    tick={{ fill: "#9ca3af", fontSize: 11, fontWeight: 500 }}
                  />
                  <PolarRadiusAxis
                    angle={30}
                    domain={[0, 100]}
                    tick={false}
                    axisLine={false}
                  />
                  <Radar
                    name="Skill"
                    dataKey="score"
                    stroke={persona.color}
                    fill={persona.color}
                    fillOpacity={0.15}
                    strokeWidth={2}
                    dot={{ r: 4, fill: persona.color }}
                  />
                </RadarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {/* ═══ Footer ═══ */}
        <div className="pt-2 border-t border-surface-3/30 text-center">
          <p className="text-xs text-gray-600">
            Based on deep analysis of {identity.analyzed_games} games out of {identity.total_games} total.
            This report is fully deterministic — no AI, no randomness, just your data.
          </p>
        </div>
      </div>
    </Card>
  );
}

// ─── Section Header ─────────────────────────────────────

function SectionHeader({
  icon,
  title,
  overrideTitle,
  color,
}: {
  icon: string;
  title: string;
  overrideTitle?: string;
  color: string;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-base">{icon}</span>
      <h3 className="text-xs font-bold uppercase tracking-wider" style={{ color }}>
        {overrideTitle || title}
      </h3>
    </div>
  );
}

// ─── Phase Column ───────────────────────────────────────

function PhaseColumn({
  label,
  cpl,
}: {
  label: string;
  cpl: number | null;
}) {
  const acc = cplToAccuracy(cpl);
  const color = accuracyColor(acc);

  // Bar height: normalize accuracy to percentage
  const barPct = acc !== null ? acc : 0;

  const barColor =
    acc === null
      ? "bg-surface-3"
      : acc >= 90
      ? "bg-green-500"
      : acc >= 75
      ? "bg-green-400"
      : acc >= 60
      ? "bg-yellow-500"
      : acc >= 45
      ? "bg-orange-500"
      : "bg-red-500";

  return (
    <div className="text-center">
      <p className="text-sm text-gray-400 mb-2">{label}</p>
      <div className="h-32 bg-surface-2 rounded-lg flex items-end justify-center pb-0 overflow-hidden">
        {acc !== null ? (
          <div
            className={`w-10 ${barColor} rounded-t transition-all duration-500`}
            style={{ height: `${Math.max(8, barPct)}%` }}
          />
        ) : (
          <span className="text-gray-600 text-xs pb-4">No data</span>
        )}
      </div>
      <p className={`text-xl font-bold mt-2 ${color}`}>
        {acc !== null ? `${acc}%` : "—"}
      </p>
      <p className="text-xs text-gray-500">accuracy</p>
    </div>
  );
}
