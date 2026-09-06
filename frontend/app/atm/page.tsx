"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Banknote, Headset, QrCode, RotateCcw, WifiOff } from "lucide-react";
import { ApiError, atmDaemon } from "@/lib/api";
import type { AtmDaemonState } from "@/types/api";

const POLL_INTERVAL_MS = 1000;
const AMOUNTS = [50_000, 100_000, 300_000, 500_000];

/**
 * ATM 7인치 터치 디스플레이 (FR-10).
 * 라즈베리파이 로컬 데몬(pi/main.py)의 /state를 폴링한다 — 위험 판단과 현금 배출
 * 제어는 전부 파이 안에서 끝나므로 이 화면은 상태를 크게 보여주는 역할만 한다.
 */
export default function AtmScreen() {
  const [state, setState] = useState<AtmDaemonState | null>(null);
  const [daemonError, setDaemonError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setState(await atmDaemon.get<AtmDaemonState>("/state"));
      setDaemonError(null);
    } catch (err) {
      setDaemonError(
        err instanceof ApiError ? err.message : "ATM 제어 장치에 연결할 수 없습니다.",
      );
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = setInterval(refresh, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [refresh]);

  const withdraw = async (amount: number) => {
    setNotice(null);
    try {
      const next = await atmDaemon.post<AtmDaemonState & { dispensed: boolean }>("/withdraw", {
        amount,
      });
      setState(next);
      setNotice(
        next.dispensed
          ? `${amount.toLocaleString("ko-KR")}원을 배출했습니다.`
          : "현금이 나오지 않습니다. 보이스피싱 위험으로 출금이 멈춰 있습니다.",
      );
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : "출금 요청을 처리하지 못했습니다.");
    }
  };

  const callCenter = async () => {
    setState(await atmDaemon.post<AtmDaemonState>("/call-center"));
    setNotice(null);
  };

  const reset = async () => {
    setState(await atmDaemon.post<AtmDaemonState>("/reset"));
    setNotice(null);
  };

  if (daemonError) {
    return (
      <AtmShell tone="neutral">
        <AlertTriangle size={72} className="text-slate-400" aria-hidden />
        <p className="text-3xl font-bold text-slate-800">ATM 제어 장치에 연결할 수 없습니다</p>
        <p className="text-xl text-slate-500 break-keep">{daemonError}</p>
      </AtmShell>
    );
  }

  if (!state) {
    return (
      <AtmShell tone="neutral">
        <p className="text-3xl text-slate-500">준비 중입니다...</p>
      </AtmShell>
    );
  }

  const blocked = state.state === "WITHDRAW_BLOCKED" || state.state === "CALL_CENTER";

  return (
    <AtmShell tone={blocked ? "danger" : "neutral"}>
      {state.offline && (
        <p className="flex items-center gap-2 rounded-xl bg-amber-100 px-4 py-2 text-lg text-amber-900">
          <WifiOff size={22} aria-hidden />
          서버에 연결되지 않아 QR 정보만으로 판단하고 있습니다
        </p>
      )}

      {state.state === "READY" && (
        <>
          <QrCode size={96} className="text-sky-700" aria-hidden />
          <p className="text-4xl font-bold leading-snug text-slate-900 break-keep">
            {state.guidance}
          </p>
        </>
      )}

      {state.state === "WITHDRAW_ENABLED" && (
        <>
          <Banknote size={80} className="text-emerald-600" aria-hidden />
          <p className="text-4xl font-bold text-slate-900">{state.guidance}</p>
          <AmountGrid onSelect={withdraw} />
        </>
      )}

      {blocked && (
        <>
          <AlertTriangle size={96} className="text-rose-600" aria-hidden />
          <p className="text-5xl font-extrabold leading-snug text-rose-800 break-keep">
            {state.guidance}
          </p>

          {state.reasons.length > 0 && (
            <ul className="w-full space-y-2 rounded-2xl bg-white p-6 text-2xl text-slate-800">
              {state.reasons.map((reason) => (
                <li key={reason} className="break-keep">
                  · {reason}
                </li>
              ))}
            </ul>
          )}

          {/* 출금 버튼은 그대로 둔다 — 눌러도 현금이 나오지 않는 것을 보여주는 것이
              이 프로젝트의 핵심 시연 장면이다 (PRD 9.2 / FR-09) */}
          <AmountGrid onSelect={withdraw} />

          {/* 상담원이 이미 결론을 냈다면 다시 요청하게 두지 않는다 */}
          {state.state === "WITHDRAW_BLOCKED" && !state.callcenter_resolution && (
            <button type="button" onClick={callCenter} className="btn-danger flex items-center justify-center gap-3">
              <Headset size={32} aria-hidden />
              상담원 확인 요청하기
            </button>
          )}
        </>
      )}

      {notice && (
        <p
          role="status"
          className="w-full rounded-2xl bg-slate-900 px-6 py-5 text-center text-2xl font-bold text-white break-keep"
        >
          {notice}
        </p>
      )}

      {state.last_error && (
        <p role="alert" className="w-full rounded-2xl bg-amber-100 px-6 py-4 text-center text-2xl text-amber-900 break-keep">
          {state.last_error}
        </p>
      )}

      <footer className="flex w-full items-center justify-between gap-4 pt-4 text-lg text-slate-500">
        <span className="font-mono">{state.session_id ?? "세션 없음"}</span>
        <button
          type="button"
          onClick={reset}
          className="inline-flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2 hover:bg-slate-200"
        >
          <RotateCcw size={20} aria-hidden />
          처음으로
        </button>
      </footer>
    </AtmShell>
  );
}

function AmountGrid({ onSelect }: { onSelect: (amount: number) => void }) {
  return (
    <div className="grid w-full grid-cols-2 gap-4">
      {AMOUNTS.map((amount) => (
        <button
          key={amount}
          type="button"
          onClick={() => onSelect(amount)}
          className="cursor-pointer rounded-2xl border-4 border-slate-800 bg-white px-4 py-7 text-3xl font-bold text-slate-900 transition-colors duration-200 hover:bg-slate-100"
        >
          {amount.toLocaleString("ko-KR")}원
        </button>
      ))}
    </div>
  );
}

function AtmShell({
  tone,
  children,
}: {
  tone: "neutral" | "danger";
  children: React.ReactNode;
}) {
  return (
    <main
      className={`flex min-h-screen w-full flex-col items-center justify-center gap-7 p-8 transition-colors duration-200 ${
        tone === "danger" ? "bg-rose-100" : "bg-slate-100"
      }`}
    >
      <div className="flex w-full max-w-3xl flex-col items-center gap-7 text-center">
        {children}
      </div>
    </main>
  );
}
