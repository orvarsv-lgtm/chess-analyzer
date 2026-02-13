import { cn } from "@/lib/utils";
import { forwardRef } from "react";

// ─── Card ───────────────────────────────────────────────

export function Card({
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-xl bg-surface-1 border border-surface-3",
        className
      )}
      {...props}
    >
      {children}
    </div>
  );
}

export function CardHeader({
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("px-5 pt-5 pb-0", className)} {...props}>
      {children}
    </div>
  );
}

export function CardContent({
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("px-5 py-4", className)} {...props}>
      {children}
    </div>
  );
}

// ─── Button ─────────────────────────────────────────────

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
  loading?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "primary", size = "md", loading, disabled, children, ...props }, ref) => {
    const base =
      "inline-flex items-center justify-center font-medium rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-brand-600/50 disabled:opacity-50 disabled:cursor-not-allowed";

    const variants = {
      primary: "bg-brand-600 text-white hover:bg-brand-700",
      secondary: "bg-surface-2 text-gray-300 hover:bg-surface-3 border border-surface-3",
      ghost: "text-gray-400 hover:bg-surface-2 hover:text-white",
      danger: "bg-red-600/20 text-red-400 hover:bg-red-600/30",
    };

    const sizes = {
      sm: "px-3 py-1.5 text-xs gap-1.5",
      md: "px-4 py-2.5 text-sm gap-2",
      lg: "px-6 py-3 text-base gap-2",
    };

    return (
      <button
        ref={ref}
        className={cn(base, variants[variant], sizes[size], className)}
        disabled={disabled || loading}
        {...props}
      >
        {loading && <Spinner className="h-4 w-4" />}
        {children}
      </button>
    );
  }
);
Button.displayName = "Button";

// ─── Badge ──────────────────────────────────────────────

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: "default" | "success" | "warning" | "danger" | "info";
}

export function Badge({
  variant = "default",
  className,
  children,
  ...props
}: BadgeProps) {
  const variants = {
    default: "bg-surface-2 text-gray-400",
    success: "bg-green-900/40 text-green-400",
    warning: "bg-yellow-900/40 text-yellow-400",
    danger: "bg-red-900/40 text-red-400",
    info: "bg-brand-900/40 text-brand-400",
  };

  return (
    <span
      className={cn(
        "inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium",
        variants[variant],
        className
      )}
      {...props}
    >
      {children}
    </span>
  );
}

// ─── Spinner ────────────────────────────────────────────

export function Spinner({ className }: { className?: string }) {
  return (
    <svg
      className={cn("animate-spin text-current", className)}
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
    >
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
      />
    </svg>
  );
}

// ─── EmptyState ─────────────────────────────────────────

interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
}

export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-12 px-6 text-center">
      {icon && <div className="text-gray-600 mb-4">{icon}</div>}
      <h3 className="text-lg font-semibold text-gray-300 mb-1">{title}</h3>
      {description && (
        <p className="text-sm text-gray-500 max-w-sm mb-4">{description}</p>
      )}
      {action}
    </div>
  );
}

// ─── Stat Card ──────────────────────────────────────────

interface StatCardProps {
  label: string;
  value: string | number;
  subtitle?: string;
  icon?: React.ReactNode;
  trend?: "up" | "down" | "neutral";
}

export function StatCard({ label, value, subtitle, icon, trend }: StatCardProps) {
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs text-gray-500 uppercase tracking-wider">
            {label}
          </p>
          <p className="text-2xl font-bold mt-1">{value}</p>
          {subtitle && (
            <p
              className={cn(
                "text-xs mt-1",
                trend === "up"
                  ? "text-green-400"
                  : trend === "down"
                  ? "text-red-400"
                  : "text-gray-500"
              )}
            >
              {subtitle}
            </p>
          )}
        </div>
        {icon && <div className="text-gray-500">{icon}</div>}
      </div>
    </Card>
  );
}

// ─── Move quality color helpers ─────────────────────────

export function moveQualityColor(quality: string | null): string {
  switch (quality) {
    case "Brilliant":
      return "text-cyan-300";
    case "Great":
      return "text-blue-400";
    case "Best":
      return "text-cyan-400";
    case "Excellent":
      return "text-green-400";
    case "Good":
      return "text-green-300";
    case "Forced":
      return "text-gray-400";
    case "Inaccuracy":
      return "text-yellow-400";
    case "Mistake":
      return "text-orange-400";
    case "Missed Win":
      return "text-orange-500";
    case "Blunder":
      return "text-red-400";
    default:
      return "text-gray-400";
  }
}

export function moveQualityBg(quality: string | null): string {
  switch (quality) {
    case "Brilliant":
      return "bg-cyan-300/10";
    case "Great":
      return "bg-blue-400/10";
    case "Best":
      return "bg-cyan-400/10";
    case "Excellent":
      return "bg-green-400/10";
    case "Good":
      return "bg-green-300/10";
    case "Forced":
      return "bg-gray-400/10";
    case "Inaccuracy":
      return "bg-yellow-400/10";
    case "Mistake":
      return "bg-orange-400/10";
    case "Missed Win":
      return "bg-orange-500/10";
    case "Blunder":
      return "bg-red-400/10";
    default:
      return "bg-surface-2";
  }
}

export function resultColor(result: string): string {
  switch (result) {
    case "win":
      return "text-green-400";
    case "loss":
      return "text-red-400";
    case "draw":
      return "text-yellow-400";
    default:
      return "text-gray-400";
  }
}

export function resultBadgeVariant(
  result: string
): "success" | "danger" | "warning" | "default" {
  switch (result) {
    case "win":
      return "success";
    case "loss":
      return "danger";
    case "draw":
      return "warning";
    default:
      return "default";
  }
}
