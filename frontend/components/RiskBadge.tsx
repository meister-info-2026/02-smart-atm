import { AlertTriangle, ShieldAlert, ShieldCheck } from "lucide-react";
import type { RiskLevel } from "@/types/api";

/**
 * 위험 등급 표시. 색만으로 구분하지 않고 텍스트와 아이콘을 함께 쓴다
 * (PRD 5.1 노약자 UI 원칙 / ui-ux-rules.md 색상 의미 고정).
 */
const RISK_STYLES: Record<
  RiskLevel,
  { label: string; className: string; Icon: typeof ShieldCheck }
> = {
  SAFE: {
    label: "안전",
    className: "bg-emerald-50 text-emerald-800 border-emerald-300",
    Icon: ShieldCheck,
  },
  CAUTION: {
    label: "의심",
    className: "bg-amber-50 text-amber-800 border-amber-300",
    Icon: AlertTriangle,
  },
  DANGER: {
    label: "위험",
    className: "bg-rose-50 text-rose-800 border-rose-300",
    Icon: ShieldAlert,
  },
};

interface RiskBadgeProps {
  level: RiskLevel;
  size?: "md" | "lg";
}

export function RiskBadge({ level, size = "md" }: RiskBadgeProps) {
  const { label, className, Icon } = RISK_STYLES[level];
  const sizing =
    size === "lg" ? "gap-3 px-6 py-3 text-3xl" : "gap-2 px-3 py-1.5 text-base";
  const iconSize = size === "lg" ? 36 : 20;

  return (
    <span
      className={`inline-flex items-center rounded-full border-2 font-bold ${sizing} ${className}`}
    >
      <Icon size={iconSize} aria-hidden />
      {label}
    </span>
  );
}

export function riskLabel(level: RiskLevel): string {
  return RISK_STYLES[level].label;
}
