"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  Banknote,
  Headset,
  KeyRound,
  QrCode,
  RotateCcw,
  Timer,
  WifiOff,
} from "lucide-react";
import { VoiceToggle } from "@/components/VoiceToggle";
import { useSpeech } from "@/hooks/useSpeech";
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
  // '처음으로'가 거절당했을 때만 직원 해제 버튼을 꺼내 놓는다 (평소에는 없다)
  const [askStaff, setAskStaff] = useState(false);
  const speech = useSpeech();
  const lastStateRef = useRef<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const next = await atmDaemon.get<AtmDaemonState>("/state");
      // 상태가 바뀌면 직전 안내(예: "현금이 나오지 않습니다")는 치운다.
      // 상담원이 제한을 풀어 화면이 초록으로 바뀌었는데 그 문구가 남아 있으면
      // 어르신은 아직 막혀 있다고 읽는다.
      if (lastStateRef.current !== null && lastStateRef.current !== next.state) {
        setNotice(null);
        setAskStaff(false);
      }
      lastStateRef.current = next.state;
      setState(next);
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

  // 지금 화면에서 가장 중요한 한 문장을 읽는다.
  // 방금 일어난 일(notice) > 오류 > 평상시 안내 순서다.
  useEffect(() => {
    if (notice) {
      speech.announce(`notice:${notice}`, notice);
      return;
    }
    if (state?.last_error) {
      speech.announce(`error:${state.last_error}`, state.last_error);
      return;
    }
    if (state) {
      speech.announce(
        `state:${state.state}:${state.callcenter_resolution ?? "-"}`,
        state.guidance,
      );
    }
  }, [notice, state, speech]);

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

  // '처음으로'는 화면을 정리하는 버튼이지 제한을 푸는 버튼이 아니다.
  // 이 버튼으로 차단이 풀린다면 막힌 사람은 그냥 이걸 누르면 그만이다.
  const reset = async () => {
    const next = await atmDaemon.post<AtmDaemonState & { reset: boolean }>("/reset");
    setState(next);
    if (next.reset) {
      setNotice(null);
      setAskStaff(false);
      return;
    }
    // 왜 거절됐는지에 따라 다르게 말한다 — 설정 오류인데 "보이스피싱"이라고
    // 하면, 고쳐야 할 사람이 엉뚱한 곳을 뒤진다
    if (next.state === "CALL_CENTER") {
      setNotice("상담원이 확인 중입니다. 확인이 끝나거나 은행 직원이 해제해야 열립니다.");
    } else if (next.restricted) {
      setNotice("보이스피싱 확인으로 잠긴 화면입니다. 은행 직원이 확인해야 다시 열립니다.");
    } else {
      setNotice("설정 오류로 멈춰 있습니다. 아래 안내대로 고친 뒤 다시 시작해 주세요.");
    }
    setAskStaff(true);
  };

  // 은행 직원 확인. 서버의 판정을 지우는 것이 아니라 기계를 다음 사람에게 넘기는
  // 것이므로, 같은 QR을 다시 비추면 즉시 다시 막힌다.
  const staffRelease = async () => {
    setState(await atmDaemon.post<AtmDaemonState>("/staff-release"));
    setNotice(null);
    setAskStaff(false);
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

  // 제한 여부는 데몬이 판단한 값을 그대로 쓴다 — 같은 규칙을 화면에서 또 적으면
  // 언젠가 둘이 어긋난다 (어긋나는 순간 화면이 거짓말을 한다)
  const blocked = state.restricted;
  // 출금 화면도 차단 화면도 아닌 상태 — 확인을 하지 못해 잠시 멈춘 화면이다.
  // 여기에 아무 그림도 제목도 없으면 노란 띠 한 줄만 떠 있는 허전한 화면이 된다.
  const halted = !state.can_withdraw && !blocked;

  return (
    <AtmShell tone={blocked ? "danger" : "neutral"}>
      {state.offline && (
        <p className="flex items-center gap-2 rounded-xl bg-amber-100 px-4 py-2 text-lg text-amber-900">
          <WifiOff size={22} aria-hidden />
          서버에 연결되지 않아 QR 정보만으로 판단하고 있습니다
        </p>
      )}

      {/* ATM은 공용 기계다. 평상시에는 보통 ATM처럼 돈이 나오고, 위험이 확인된
          세션에서만 막는다. QR을 못 내민다고 막으면 이 시스템과 아무 상관 없는
          사람까지 출금하지 못한다 */}
      {state.can_withdraw && (
        <>
          <Banknote size={80} className="text-emerald-600" aria-hidden />
          <p className="text-4xl font-bold text-slate-900 break-keep">{state.guidance}</p>
          <AmountGrid onSelect={withdraw} />

          {/* 아직 아무 QR도 읽지 않은 평상시에만, 이 기계가 무엇을 더 할 수 있는지 알린다 */}
          {state.state === "READY" && (
            <p className="flex items-center gap-3 text-xl text-slate-500 break-keep">
              <QrCode size={26} className="shrink-0 text-sky-700" aria-hidden />
              보이스피싱 검사 QR이 있으시면 카메라에 보여 주세요
            </p>
          )}
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

      {halted && (
        <>
          <AlertTriangle size={88} className="text-amber-500" aria-hidden />
          <p className="text-4xl font-bold leading-snug text-slate-900 break-keep">
            {state.last_error ?? "잠시만 기다려 주세요"}
          </p>
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

      {askStaff && (
        <button
          type="button"
          onClick={staffRelease}
          /* 손님용 버튼처럼 보이면 안 된다 — 금액 버튼과 크기·굵기를 확실히 다르게 둔다 */
          className="inline-flex cursor-pointer items-center gap-2 rounded-xl border-2 border-slate-400 bg-white px-5 py-3 text-lg font-medium text-slate-700 transition-colors duration-200 hover:bg-slate-50"
        >
          <KeyRound size={28} aria-hidden />
          직원 확인 후 해제
        </button>
      )}

      {/* 이미 큰 글씨로 띄운 문구(halted)를 아래에 또 적지 않는다 */}
      {state.last_error && !halted && (
        <div role="alert" className="w-full rounded-2xl bg-amber-100 px-6 py-4 text-center break-keep">
          <p className="text-2xl text-amber-900">{state.last_error}</p>
        </div>
      )}

      {/* 어르신께 드리는 안내와 고치는 사람에게 주는 단서를 분리한다.
          작게 두어 시연을 방해하지 않으면서, 원인을 찾아 헤매지 않게 한다 */}
      {state.operator_hint && (
        <p className="w-full rounded-xl bg-amber-100 px-5 py-3 text-center font-mono text-sm text-amber-800 break-keep">
          {state.operator_hint}
        </p>
      )}

      {/* 다음 사람을 위한 자동 초기화. 상담원을 기다리는 동안에는 데몬이 세지 않으므로
          이 줄도 뜨지 않는다 — 기다리는 시간은 노는 시간이 아니다 */}
      {state.idle_reset_in !== null && <IdleCountdown seconds={state.idle_reset_in} />}

      <footer className="flex w-full flex-wrap items-center justify-between gap-4 pt-4 text-lg text-slate-500">
        <span className="font-mono">{state.session_id ?? "세션 없음"}</span>
        <div className="flex items-center gap-3">
          <VoiceToggle speech={speech} />
          <button
            type="button"
            onClick={reset}
            className="inline-flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2 hover:bg-slate-200"
          >
            <RotateCcw size={20} aria-hidden />
            처음으로
          </button>
        </div>
      </footer>
    </AtmShell>
  );
}

function IdleCountdown({ seconds }: { seconds: number }) {
  // 마지막 10초는 눈에 띄게 — 관람객이 "곧 다음 사람 차례"라는 걸 알아야 한다
  const urgent = seconds <= 10;
  return (
    <p
      role="status"
      className={`flex items-center gap-3 rounded-xl px-5 py-3 text-xl break-keep transition-colors duration-200 ${
        urgent ? "bg-slate-900 text-white" : "text-slate-500"
      }`}
    >
      <Timer size={24} className="shrink-0" aria-hidden />
      <span>
        <strong className="font-mono tabular-nums">{seconds}</strong>초 뒤 처음 화면으로 돌아갑니다
      </span>
    </p>
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
