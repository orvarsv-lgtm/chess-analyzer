"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import Link from "next/link";
import {
  ArrowLeft,
  ArrowRight,
  Sparkles,
  Target,
  TrendingUp,
  TrendingDown,
  Shield,
  AlertTriangle,
  Dumbbell,
  ChevronRight,
  Flame,
  BookOpen,
  Clock,
  Zap,
} from "lucide-react";
import {
  insightsAPI,
  type CoachReport,
  type TrainingAction,
  type PhaseReportItem,
  type HonestTruth,
  type GrowthStep,
} from "@/lib/api";
import { Card, CardContent, Badge, Button, Spinner, EmptyState } from "@/components/ui";

// ─── Tier colors & badges ───────────────────────────────

const TIER_COLORS: Record<string, { bg: string; text: string; ring: string; badge: string }> = {
  beginner: { bg: "from-emerald-900/30 to-emerald-800/10", text: "text-emerald-400", ring: "ring-emerald-500/30", badge: "bg-emerald-900/40 text-emerald-400" },
  intermediate: { bg: "from-blue-900/30 to-blue-800/10", text: "text-blue-400", ring: "ring-blue-500/30", badge: "bg-blue-900/40 text-blue-400" },
  advanced: { bg: "from-purple-900/30 to-purple-800/10", text: "text-purple-400", ring: "ring-purple-500/30", badge: "bg-purple-900/40 text-purple-400" },
  expert: { bg: "from-amber-900/30 to-amber-800/10", text: "text-amber-400", ring: "ring-amber-500/30", badge: "bg-amber-900/40 text-amber-400" },
};

// ─── Phase icons ────────────────────────────────────────

const PHASE_ICONS: Record<string, typeof BookOpen> = {
  Opening: BookOpen,
  Middlegame: Zap,
  Endgame: Target,
};

// ─── Priority colors for growth steps ───────────────────

const PRIORITY_STYLES: Record<string, { dot: string; border: string }> = {
  high: { dot: "bg-red-400", border: "border-l-red-500/60" },
  medium: { dot: "bg-yellow-400", border: "border-l-yellow-500/60" },
  low: { dot: "bg-green-400", border: "border-l-green-500/60" },
};

export default function CoachReportPage() {
  const { data: session, status: authStatus } = useSession();
  const [report, setReport] = useState<CoachReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (authStatus !== "authenticated") return;
    loadReport();
  }, [authStatus]);

  async function loadReport() {
    try {
      setLoading(true);
      setError(null);
      const data = await insightsAPI.coachReport();
      setReport(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load coach report");
    } finally {
      setLoading(false);
    }
  }

  if (authStatus === "loading" || loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-center space-y-4">
          <Spinner className="h-8 w-8 mx-auto" />
          <div>
            <p className="text-white font-medium">Generating your coach report...</p>
            <p className="text-sm text-gray-500 mt-1">Analyzing your games, patterns, and tendencies</p>
          </div>
        </div>
      </div>
    );
  }

  if (authStatus !== "authenticated") {
    return (
      <div className="p-6">
        <EmptyState title="Sign in to view your AI Coach Report" description="Your personalized coaching analysis awaits." />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 space-y-4">
        <BackLink />
        <Card>
          <CardContent>
            <div className="text-center py-8">
              <AlertTriangle className="h-8 w-8 text-yellow-400 mx-auto mb-3" />
              <p className="text-white font-medium">Couldn&apos;t load your report</p>
              <p className="text-sm text-gray-400 mt-1">{error}</p>
              <Button variant="secondary" size="sm" className="mt-4" onClick={loadReport}>
                Try Again
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!report || !report.has_data) {
    return (
      <div className="p-6 space-y-4">
        <BackLink />
        <Card>
          <CardContent>
            <EmptyState
              title="Not enough data yet"
              description={report?.message || "Analyze at least 3 games to generate your AI Coach Report."}
            />
          </CardContent>
        </Card>
      </div>
    );
  }

  const tier = report.elo_tier || "intermediate";
  const colors = TIER_COLORS[tier] || TIER_COLORS.intermediate;

  return (
    <div className="max-w-3xl mx-auto px-4 py-6 space-y-6">
      <BackLink />

      {/* ═══ Header ═══ */}
      <div className={`rounded-2xl bg-gradient-to-br ${colors.bg} border border-surface-3 p-6 md:p-8`}>
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <span className="text-4xl">{report.persona?.emoji || "♟️"}</span>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <h1 className="text-xl md:text-2xl font-bold text-white">
                  AI Coach Report
                </h1>
                <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${colors.badge}`}>
                  {report.elo_tier_label}
                </span>
              </div>
              <p className="text-sm text-gray-400 mt-0.5">
                {report.persona?.name || "Your"} · {report.elo ? `${report.elo} ELO` : "Unrated"}
                {report.elo_trend != null && report.elo_trend !== 0 && (
                  <span className={report.elo_trend > 0 ? "text-green-400 ml-1.5" : "text-red-400 ml-1.5"}>
                    {report.elo_trend > 0 ? "+" : ""}{report.elo_trend} last 30
                  </span>
                )}
              </p>
            </div>
          </div>
          <Sparkles className={`h-5 w-5 ${colors.text} opacity-60`} />
        </div>

        {/* Headline */}
        {report.headline && (
          <p className="mt-5 text-base md:text-lg font-medium text-white/90 leading-relaxed">
            {report.headline}
          </p>
        )}

        <p className="text-xs text-gray-500 mt-4">
          Based on {report.analyzed_games} analyzed games
        </p>
      </div>

      {/* ═══ Honest Truths ═══ */}
      {report.honest_truths && report.honest_truths.length > 0 && (
        <section className="space-y-3">
          <SectionHeader icon={AlertTriangle} title="Let's Be Honest" />
          <div className="space-y-2">
            {report.honest_truths.map((truth, i) => (
              <HonestTruthCard key={i} truth={truth} />
            ))}
          </div>
        </section>
      )}

      {/* ═══ Chess Story ═══ */}
      {report.chess_story && (
        <section className="space-y-3">
          <SectionHeader icon={BookOpen} title="Your Chess Story" />
          <Card>
            <CardContent>
              <p className="text-gray-300 leading-relaxed text-sm md:text-base">
                {report.chess_story}
              </p>
            </CardContent>
          </Card>
        </section>
      )}

      {/* ═══ Phase Report ═══ */}
      {report.phase_report && report.phase_report.length > 0 && (
        <section className="space-y-3">
          <SectionHeader icon={Target} title="Phase-by-Phase Breakdown" />
          <div className="space-y-2">
            {report.phase_report.map((phase) => (
              <PhaseCard key={phase.phase} phase={phase} tier={tier} />
            ))}
          </div>
        </section>
      )}

      {/* ═══ Kryptonite ═══ */}
      {report.kryptonite && (
        <section className="space-y-3">
          <SectionHeader icon={Shield} title="Your Kryptonite" />
          <Card className="border-l-4 border-l-red-500/40">
            <CardContent className="flex items-start gap-3">
              <span className="text-2xl mt-0.5">⚠️</span>
              <div className="flex-1 min-w-0">
                <p className="text-white font-medium text-sm">{report.kryptonite.area}</p>
                <p className="text-gray-400 text-sm mt-1">{report.kryptonite.message}</p>
                <KryptoniteCTA area={report.kryptonite.area} />
              </div>
            </CardContent>
          </Card>
        </section>
      )}

      {/* ═══ Training Plan ═══ */}
      {report.training_plan && report.training_plan.length > 0 && (
        <section className="space-y-3">
          <SectionHeader icon={Dumbbell} title="Your Training Plan" />
          <div className="space-y-3">
            {report.training_plan.map((action, i) => (
              <TrainingActionCard key={i} action={action} index={i} tierColor={colors.text} />
            ))}
          </div>
        </section>
      )}

      {/* ═══ Growth Path ═══ */}
      {report.growth_path && report.growth_path.length > 0 && (
        <section className="space-y-3">
          <SectionHeader icon={TrendingUp} title="Growth Path" />
          <div className="space-y-2">
            {report.growth_path.map((step, i) => (
              <GrowthStepCard key={i} step={step} />
            ))}
          </div>
        </section>
      )}

      {/* ═══ Today's Focus ═══ */}
      {report.today_focus && (
        <section className="space-y-3">
          <SectionHeader icon={Flame} title={`Today's Focus: ${report.today_focus.focus}`} />
          <Card>
            <CardContent className="space-y-2">
              {report.today_focus.activities.map((act, i) => (
                <div key={i} className="flex items-center justify-between py-1.5">
                  <div className="flex items-center gap-2">
                    <Clock className="h-3.5 w-3.5 text-gray-500" />
                    <span className="text-sm text-gray-300">{act.name}</span>
                  </div>
                  <span className="text-xs text-gray-500">{act.duration_min} min</span>
                </div>
              ))}
              <Link
                href="/train?mode=warmup"
                className="flex items-center gap-2 text-sm font-medium text-brand-400 hover:text-brand-300 transition-colors mt-3 pt-2 border-t border-surface-3"
              >
                Start Training <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            </CardContent>
          </Card>
        </section>
      )}

      {/* ═══ One Thing ═══ */}
      {report.one_thing && (
        <div className={`rounded-2xl bg-gradient-to-br ${colors.bg} border border-surface-3 p-6 text-center`}>
          <p className="text-xs uppercase tracking-wider text-gray-500 mb-2">
            If You Do One Thing This Week
          </p>
          <p className="text-lg md:text-xl font-semibold text-white leading-relaxed">
            {report.one_thing}
          </p>
          <Link
            href="/train?mode=warmup"
            className={`inline-flex items-center gap-2 mt-4 text-sm font-medium ${colors.text} hover:opacity-80 transition-opacity`}
          >
            Start Training <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      )}

      {/* ═══ Week Overview ═══ */}
      {report.week_themes && report.week_themes.length > 0 && (
        <section className="space-y-3">
          <SectionHeader icon={Clock} title="This Week's Plan" />
          <Card>
            <CardContent>
              <div className="grid grid-cols-7 gap-1">
                {report.week_themes.map((wt, i) => (
                  <div
                    key={i}
                    className={`text-center py-2 px-1 rounded-lg ${
                      report.today_focus?.day === wt.day
                        ? "bg-brand-600/20 ring-1 ring-brand-500/30"
                        : "bg-surface-2/50"
                    }`}
                  >
                    <p className="text-[10px] text-gray-500 font-medium">{wt.day.slice(0, 3)}</p>
                    <p className="text-[10px] text-gray-400 mt-0.5 leading-tight truncate">{wt.focus}</p>
                  </div>
                ))}
              </div>
              <Link
                href="/insights"
                className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-400 transition-colors mt-3"
              >
                View full study plan on Insights
              </Link>
            </CardContent>
          </Card>
        </section>
      )}

      {/* Footer */}
      <div className="text-center pb-8">
        <p className="text-xs text-gray-600">
          This report is auto-generated from your game data. No AI language models — just pure data analysis.
        </p>
      </div>
    </div>
  );
}

// ─── Sub-components ────────────────────────────────────

function BackLink() {
  return (
    <Link
      href="/insights"
      className="inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-300 transition-colors"
    >
      <ArrowLeft className="h-3.5 w-3.5" />
      Back to Insights
    </Link>
  );
}

function SectionHeader({ icon: Icon, title }: { icon: typeof Target; title: string }) {
  return (
    <div className="flex items-center gap-2 pt-2">
      <Icon className="h-4 w-4 text-gray-500" />
      <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">{title}</h2>
      <div className="flex-1 h-px bg-surface-3 ml-2" />
    </div>
  );
}

function HonestTruthCard({ truth }: { truth: HonestTruth }) {
  return (
    <Card className="border-l-4 border-l-yellow-500/40 hover:border-l-yellow-500/60 transition-colors">
      <CardContent className="flex items-start gap-3 py-3.5">
        <span className="text-lg mt-0.5 shrink-0">{truth.icon}</span>
        <div className="flex-1 min-w-0">
          <p className="text-sm text-gray-300 leading-relaxed">{truth.text}</p>
          {truth.cta_url && truth.cta_label && (
            <Link
              href={truth.cta_url}
              className="inline-flex items-center gap-1.5 text-xs font-medium text-brand-400 hover:text-brand-300 transition-colors mt-2.5 bg-brand-600/10 px-2.5 py-1 rounded-md"
            >
              {truth.cta_label} <ArrowRight className="h-3 w-3" />
            </Link>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function PhaseCard({ phase, tier }: { phase: PhaseReportItem; tier: string }) {
  const Icon = PHASE_ICONS[phase.phase] || Target;
  const tagColors: Record<string, string> = {
    strongest: "bg-green-900/40 text-green-400",
    weakest: "bg-red-900/40 text-red-400",
    neutral: "bg-surface-2 text-gray-400",
  };
  // Convert CPL to a quality bar (lower CPL = better)
  const quality = Math.max(0, Math.min(100, Math.round(100 - phase.cpl * 0.8)));
  const barColor = phase.tag === "strongest" ? "bg-green-500" : phase.tag === "weakest" ? "bg-red-500" : "bg-brand-500";

  return (
    <Card className="overflow-hidden">
      <CardContent className="space-y-3 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className={`h-8 w-8 rounded-lg flex items-center justify-center ${
              phase.tag === "strongest" ? "bg-green-900/30" : phase.tag === "weakest" ? "bg-red-900/30" : "bg-surface-2"
            }`}>
              <Icon className={`h-4 w-4 ${
                phase.tag === "strongest" ? "text-green-400" : phase.tag === "weakest" ? "text-red-400" : "text-gray-400"
              }`} />
            </div>
            <span className="text-sm font-medium text-white">{phase.phase}</span>
            <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${tagColors[phase.tag] || tagColors.neutral}`}>
              {phase.tag === "strongest" ? "Strongest" : phase.tag === "weakest" ? "Needs Work" : "Solid"}
            </span>
          </div>
        </div>
        {/* Quality bar */}
        <div className="w-full bg-surface-2 rounded-full h-1.5">
          <div className={`${barColor} h-1.5 rounded-full transition-all duration-500`} style={{ width: `${quality}%` }} />
        </div>
        <p className="text-sm text-gray-400 leading-relaxed">{phase.commentary}</p>
        {phase.cta_url && phase.cta_label && (
          <Link
            href={phase.cta_url}
            className="inline-flex items-center gap-1.5 text-xs font-medium text-brand-400 hover:text-brand-300 transition-colors"
          >
            {phase.cta_label} <ArrowRight className="h-3 w-3" />
          </Link>
        )}
      </CardContent>
    </Card>
  );
}

function TrainingActionCard({
  action,
  index,
  tierColor,
}: {
  action: TrainingAction;
  index: number;
  tierColor: string;
}) {
  return (
    <Card className="overflow-hidden hover:border-surface-3/80 transition-colors">
      <CardContent className="space-y-3 py-4">
        <div className="flex items-start gap-3">
          <span className="flex items-center justify-center h-7 w-7 rounded-full bg-brand-600/20 text-brand-400 text-xs font-bold shrink-0 mt-0.5">
            {index + 1}
          </span>
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-semibold text-white">{action.title}</h3>
            <p className="text-sm text-gray-500 mt-1.5 leading-relaxed">{action.why}</p>
            <p className="text-sm text-gray-300 mt-2 leading-relaxed bg-surface-2/50 rounded-lg p-3">
              💡 {action.how}
            </p>
            {action.elo_note && (
              <p className="text-xs text-gray-500 mt-2 italic">📈 {action.elo_note}</p>
            )}
          </div>
        </div>
        <Link
          href={action.cta_url}
          className={`inline-flex items-center gap-2 text-sm font-medium ${tierColor} hover:opacity-80 transition-opacity ml-10 bg-brand-600/10 px-3 py-1.5 rounded-lg`}
        >
          {action.cta_label} <ChevronRight className="h-3.5 w-3.5" />
        </Link>
      </CardContent>
    </Card>
  );
}

function GrowthStepCard({ step }: { step: GrowthStep }) {
  const style = PRIORITY_STYLES[step.priority] || PRIORITY_STYLES.medium;

  return (
    <Card className={`border-l-4 ${style.border}`}>
      <CardContent className="py-3">
        <div className="flex items-start gap-2.5">
          <span className={`h-2 w-2 rounded-full mt-1.5 shrink-0 ${style.dot}`} />
          <div>
            <p className="text-sm font-medium text-white">{step.title}</p>
            <p className="text-sm text-gray-400 mt-0.5 leading-relaxed">{step.description}</p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function KryptoniteCTA({ area }: { area: string }) {
  const lower = area.toLowerCase();
  let href = "/train?mode=warmup";
  let label = "Practice Now";
  if (lower.includes("opening")) { href = "/train?phase=opening"; label = "Train Opening"; }
  else if (lower.includes("middlegame")) { href = "/train?phase=middlegame"; label = "Train Middlegame"; }
  else if (lower.includes("endgame")) { href = "/train?phase=endgame"; label = "Train Endgame"; }
  else if (lower.includes("converting") || lower.includes("advantage")) { href = "/train?mode=advantage"; label = "Practice Converting"; }
  else if (lower.includes("blunder")) { href = "/train?mode=warmup"; label = "Blunder Prevention"; }
  return (
    <Link
      href={href}
      className="inline-flex items-center gap-1.5 text-xs font-medium text-red-400 hover:text-red-300 transition-colors mt-2"
    >
      {label} <ArrowRight className="h-3 w-3" />
    </Link>
  );
}
