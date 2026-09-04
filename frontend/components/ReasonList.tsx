import { Dot } from "lucide-react";

/** 탐지 근거 표시 (FR-04). 근거가 없으면 안전하다는 문장을 대신 보여준다. */
export function ReasonList({ reasons }: { reasons: string[] }) {
  if (reasons.length === 0) {
    return (
      <p className="text-xl text-slate-600">위험한 표현이 발견되지 않았습니다.</p>
    );
  }

  return (
    <ul className="space-y-3">
      {reasons.map((reason) => (
        <li key={reason} className="flex items-start gap-1 text-xl text-slate-800">
          <Dot className="mt-1 shrink-0 text-rose-600" size={28} aria-hidden />
          <span className="break-keep">{reason}</span>
        </li>
      ))}
    </ul>
  );
}
