"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, Landmark, Phone } from "lucide-react";
import { QrPanel } from "@/components/QrPanel";
import { ReasonList } from "@/components/ReasonList";
import { RiskBadge } from "@/components/RiskBadge";
import { VoiceToggle } from "@/components/VoiceToggle";
import { useSpeech } from "@/hooks/useSpeech";
import { ApiError, api, readToken } from "@/lib/api";
import type { AnalysisResponse } from "@/types/api";

/** 위험 등급별 다음 행동 안내 (PRD 5.1: 다음 행동을 명확히 안내) */
/** 소리로 먼저 듣게 되는 한마디 — 화면의 배지(안전/의심/위험)와 같은 말이다 */
const RISK_SPOKEN: Record<AnalysisResponse["risk_level"], string> = {
  SAFE: "안전한 문자입니다",
  CAUTION: "의심스러운 문자입니다",
  DANGER: "위험한 문자입니다",
};

const GUIDANCE: Record<AnalysisResponse["risk_level"], string> = {
  SAFE: "위험한 내용이 없습니다. 평소처럼 은행 업무를 보셔도 됩니다.",
  CAUTION: "의심스러운 표현이 있습니다. 돈을 보내기 전에 가족이나 은행에 꼭 확인하세요.",
  DANGER: "보이스피싱 위험이 높습니다. 절대 돈을 보내거나 찾지 마세요.",
};

export default function ResultPage() {
  const params = useParams<{ analysisId: string }>();
  const router = useRouter();
  const [result, setResult] = useState<AnalysisResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const speech = useSpeech();

  const load = useCallback(async () => {
    try {
      setResult(await api.get<AnalysisResponse>(`/api/v1/analysis/${params.analysisId}`));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        router.push("/login");
        return;
      }
      setError(err instanceof ApiError ? err.message : "결과를 불러오지 못했습니다.");
    }
  }, [params.analysisId, router]);

  useEffect(() => {
    if (!readToken("user")) {
      router.push("/login");
      return;
    }
    void load();
  }, [load, router]);

  // 결과가 뜨면 판정과 다음 행동을 읽어 준다 (FR-10).
  // 글씨를 읽기 힘든 분에게는 이 한 문장이 화면 전체보다 중요하다.
  useEffect(() => {
    if (!result) return;
    speech.announce(
      `result:${result.analysis_id}`,
      `${RISK_SPOKEN[result.risk_level]}. ${GUIDANCE[result.risk_level]}`,
    );
  }, [result, speech]);

  if (error) {
    return (
      <main className="mx-auto w-full max-w-2xl px-6 py-10">
        <p role="alert" className="rounded-xl bg-rose-50 px-4 py-3 text-lg text-rose-800">
          {error}
        </p>
      </main>
    );
  }

  if (!result) {
    return <main className="mx-auto w-full max-w-2xl px-6 py-10 text-xl">불러오는 중...</main>;
  }

  const needsAtmQr = result.risk_level !== "SAFE" && result.session_id !== null;

  return (
    <main className="mx-auto w-full max-w-2xl space-y-8 px-6 py-10">
      <Link
        href="/messages"
        className="inline-flex cursor-pointer items-center gap-2 text-lg text-slate-600 hover:text-slate-900"
      >
        <ArrowLeft size={22} aria-hidden />
        다른 문자 검사하기
      </Link>

      {/* 결과 카드 — 화면에서 가장 큰 요소로 배치한다 */}
      <section className="card space-y-5 p-7">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <RiskBadge level={result.risk_level} size="lg" />
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-lg text-slate-500">위험 점수 {result.risk_score}점 / 100점</span>
            <VoiceToggle speech={speech} />
          </div>
        </div>
        <p className="text-2xl font-bold leading-relaxed text-slate-900 break-keep">
          {GUIDANCE[result.risk_level]}
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-bold text-slate-900">검사한 문자</h2>
        <p className="card p-5 text-lg leading-relaxed text-slate-700 break-keep">
          {result.message_text}
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-bold text-slate-900">이렇게 판단했습니다</h2>
        <div className="card p-5">
          <ReasonList reasons={result.reasons} />
        </div>
      </section>

      {needsAtmQr && (
        <section className="card space-y-5 border-rose-300 bg-rose-50 p-7">
          <h2 className="flex items-center gap-2 text-xl font-bold text-rose-900">
            <Landmark size={26} aria-hidden />
            ATM에서 이 QR을 보여 주세요
          </h2>
          <p className="text-lg leading-relaxed text-rose-900 break-keep">
            ATM 화면의 카메라에 이 QR 코드를 비추면, 위험이 확인되는 동안 현금 인출이 잠시
            멈춥니다.
          </p>
          <QrPanel sessionId={result.session_id as string} />
          <div className="flex items-start gap-2 rounded-xl bg-white p-4 text-lg text-slate-700 break-keep">
            <Phone className="mt-1 shrink-0 text-rose-700" size={22} aria-hidden />
            <span>
              이후 상담원이 상황을 확인합니다. 정상 거래로 확인되면 제한이 풀립니다.
            </span>
          </div>
        </section>
      )}
    </main>
  );
}
