"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, Lock, RefreshCw } from "lucide-react";
import ConnectionBadge from "@/components/dashboard/ConnectionBadge";
import { LogoutButton } from "@/components/LogoutButton";
import { ReasonList } from "@/components/ReasonList";
import { RiskBadge } from "@/components/RiskBadge";
import { useAtmSocket } from "@/hooks/useAtmSocket";
import { ApiError, api, readToken } from "@/lib/api";
import type { CallcenterSessionResponse } from "@/types/api";

const ATM_STATUS_LABEL: Record<string, string> = {
  READY: "대기",
  WITHDRAW_ENABLED: "출금 가능",
  WITHDRAW_BLOCKED: "출금 제한",
  CALL_CENTER: "상담원 확인 중",
};

/**
 * 콜센터 상담원 화면 (PRD 8 / OF-04).
 * 자동 판정을 사람이 최종 확인하는 화면이므로, 제한 해제는 반드시 여기서 사람이
 * 명시적으로 눌러야 한다 (db-rules.md 경보성 디바이스 원칙).
 */
export default function CallcenterPage() {
  const router = useRouter();
  const { connected, unauthorized, events } = useAtmSocket();
  const [sessions, setSessions] = useState<CallcenterSessionResponse[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const rows = await api.get<CallcenterSessionResponse[]>(
        "/api/v1/callcenter/sessions?only_open=false",
        { role: "agent" },
      );
      setSessions(rows);
      setError(null);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        router.push("/login?next=/callcenter");
        return;
      }
      if (err instanceof ApiError && err.status === 403) {
        // 상담원 토큰은 있으나 권한이 없다(사용자 계정으로 로그인한 경우).
        // 헤더의 '로그아웃'으로 상담원 계정으로 다시 로그인하도록 안내한다.
        setError(
          "콜센터 상담원 계정으로 로그인해야 합니다. 오른쪽 위 '로그아웃'을 누른 뒤 " +
            "callcenter 계정으로 다시 로그인해 주세요.",
        );
        return;
      }
      setError(err instanceof ApiError ? err.message : "목록을 불러오지 못했습니다.");
    }
  }, [router]);

  useEffect(() => {
    if (!readToken("agent")) {
      router.push("/login?next=/callcenter");
      return;
    }
    void load();
  }, [load, router]);

  // ATM에서 새 스캔/출금 시도가 들어오면 목록을 즉시 갱신한다
  useEffect(() => {
    if (events.length > 0) void load();
  }, [events, load]);

  const resolve = async (sessionId: string, resolution: "RELEASED" | "MAINTAINED") => {
    setBusy(true);
    try {
      await api.post(`/api/v1/callcenter/resolve/${sessionId}`, { resolution }, { role: "agent" });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "처리하지 못했습니다.");
    } finally {
      setBusy(false);
    }
  };

  const current = sessions.find((s) => s.session_id === selected) ?? sessions[0] ?? null;

  return (
    <main className="mx-auto w-full max-w-6xl space-y-6 px-6 py-8">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">콜센터 확인</h1>
          <p className="text-base text-slate-500">
            ATM에서 제한된 거래를 확인하고 유지 또는 해제를 결정합니다.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <ConnectionBadge connected={connected} />
          <LogoutButton role="agent" next="/login?next=/callcenter" />
          <button
            type="button"
            onClick={load}
            className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition-colors duration-200 hover:bg-slate-100"
          >
            <RefreshCw size={16} aria-hidden />
            새로고침
          </button>
        </div>
      </header>

      {error && (
        <p role="alert" className="rounded-xl bg-rose-50 px-4 py-3 text-base text-rose-800">
          {error}
        </p>
      )}

      {/* 목록은 보이는데 실시간 이벤트만 안 들어오는 상태를 구분해서 알려 준다 */}
      {unauthorized && !error && (
        <p role="alert" className="rounded-xl bg-amber-50 px-4 py-3 text-base text-amber-900">
          실시간 이벤트 연결이 거부되었습니다. 상담원 계정으로 다시 로그인해 주세요.
          (목록은 &lsquo;새로고침&rsquo;으로 계속 볼 수 있습니다.)
        </p>
      )}

      <div className="grid gap-6 lg:grid-cols-[22rem_1fr]">
        {/* 세션 목록 */}
        <ul className="space-y-2">
          {sessions.length === 0 && (
            <li className="card p-5 text-slate-500">확인할 세션이 없습니다.</li>
          )}
          {sessions.map((session) => (
            <li key={session.session_id}>
              <button
                type="button"
                onClick={() => setSelected(session.session_id)}
                className={`card flex w-full cursor-pointer items-center justify-between gap-3 p-4 text-left transition-colors duration-200 ${
                  current?.session_id === session.session_id
                    ? "border-sky-500 bg-sky-50"
                    : "hover:bg-slate-50"
                }`}
              >
                <span className="min-w-0">
                  <span className="block font-mono text-sm text-slate-500">
                    {session.session_id}
                  </span>
                  <span className="block truncate font-semibold text-slate-900">
                    {session.user_display_name}
                  </span>
                  <span className="text-sm text-slate-500">
                    {ATM_STATUS_LABEL[session.atm_status] ?? session.atm_status}
                    {session.callcenter_resolution &&
                      ` · ${session.callcenter_resolution === "RELEASED" ? "해제됨" : "유지됨"}`}
                  </span>
                </span>
                <RiskBadge level={session.risk_level} />
              </button>
            </li>
          ))}
        </ul>

        {/* 상세 + 처리 — 목록보다 크게 배치한다 */}
        {current ? (
          <section className="card space-y-6 p-7">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="font-mono text-sm text-slate-500">{current.session_id}</p>
                <h2 className="text-xl font-bold text-slate-900">
                  {current.user_display_name}
                </h2>
                <p className="text-sm text-slate-500">
                  탐지 {new Date(current.detected_at).toLocaleString("ko-KR")}
                  {current.scanned_at &&
                    ` · ATM 스캔 ${new Date(current.scanned_at).toLocaleTimeString("ko-KR")}`}
                </p>
              </div>
              <div className="flex flex-col items-end gap-2">
                <RiskBadge level={current.risk_level} size="lg" />
                <span className="text-sm text-slate-500">위험 점수 {current.risk_score}점</span>
              </div>
            </div>

            <div className="space-y-2">
              <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
                분석된 문자
              </h3>
              <p className="rounded-xl bg-slate-50 p-4 leading-relaxed text-slate-800 break-keep">
                {current.message_text}
              </p>
            </div>

            <div className="space-y-2">
              <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
                탐지 근거
              </h3>
              <ReasonList reasons={current.reasons} />
            </div>

            {current.callcenter_resolution ? (
              <p className="rounded-xl bg-slate-100 px-4 py-3 text-slate-700">
                이미 처리된 세션입니다 —{" "}
                <strong>
                  {current.callcenter_resolution === "RELEASED" ? "제한 해제" : "제한 유지"}
                </strong>
                {current.resolved_at &&
                  ` (${new Date(current.resolved_at).toLocaleString("ko-KR")})`}
              </p>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2">
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => resolve(current.session_id, "MAINTAINED")}
                  className="inline-flex cursor-pointer items-center justify-center gap-2 rounded-xl bg-rose-700 px-5 py-4 text-lg font-bold text-white transition-colors duration-200 hover:bg-rose-800 disabled:opacity-50"
                >
                  <Lock size={22} aria-hidden />
                  보이스피싱 — 제한 유지
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => resolve(current.session_id, "RELEASED")}
                  className="inline-flex cursor-pointer items-center justify-center gap-2 rounded-xl bg-emerald-700 px-5 py-4 text-lg font-bold text-white transition-colors duration-200 hover:bg-emerald-800 disabled:opacity-50"
                >
                  <CheckCircle2 size={22} aria-hidden />
                  정상 거래 — 제한 해제
                </button>
              </div>
            )}
          </section>
        ) : (
          <section className="card flex items-center justify-center p-10 text-slate-500">
            왼쪽에서 세션을 선택하세요.
          </section>
        )}
      </div>

      {/* 실시간 이벤트 로그 — 카드가 아니라 리스트로 (dashboard-ui-design 스킬) */}
      <section className="space-y-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          실시간 ATM 이벤트
        </h2>
        <ul className="card divide-y divide-slate-100 text-sm">
          {events.length === 0 && <li className="p-4 text-slate-400">아직 이벤트가 없습니다.</li>}
          {events.map((event, index) => (
            <li key={`${event.session_id}-${index}`} className="flex gap-3 p-3">
              <span className="font-mono text-slate-500">{event.session_id}</span>
              <span className="text-slate-800">
                {event.type === "atm_scan" && `QR 인식 · ${event.atm_status}`}
                {event.type === "withdraw_attempt" &&
                  (event.dispensed ? "출금 배출됨" : "출금 시도 차단됨")}
                {event.type === "callcenter_resolved" &&
                  `상담원 처리 · ${event.callcenter_resolution === "RELEASED" ? "해제" : "유지"}`}
              </span>
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
