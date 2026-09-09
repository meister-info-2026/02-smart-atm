"use client";

import { useEffect } from "react";
import { AlertTriangle, RotateCcw } from "lucide-react";

/**
 * ATM 화면이 예상치 못한 오류로 멈췄을 때 대신 보여 주는 화면.
 *
 * 이 화면은 전시의 핵심이다. 코드 어딘가에서 예외가 새어 나오면 React가 화면을
 * 통째로 걷어내 **아무것도 없는 흰 화면**이 되는데, 관람객 앞에서 그건 최악이다.
 * 무슨 일이 났는지 알려 주고 다시 시도할 버튼이라도 남긴다.
 *
 * 실제로 한 번 겪었다: 음성 안내가 브라우저의 speechSynthesis를 방어 없이
 * 호출해서 구현이 조금 다른 브라우저에서 화면이 통째로 사라졌다.
 */
export default function AtmError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // 원인은 개발자 도구 콘솔에 남긴다 (화면에는 기술적인 내용을 띄우지 않는다)
    console.error("[ATM 화면 오류]", error);
  }, [error]);

  return (
    <main className="flex min-h-screen w-full flex-col items-center justify-center gap-7 bg-slate-100 p-8">
      <div className="flex w-full max-w-3xl flex-col items-center gap-7 text-center">
        <AlertTriangle size={96} className="text-amber-500" aria-hidden />
        <p className="text-4xl font-bold leading-snug text-slate-900 break-keep">
          화면에 문제가 생겼습니다
        </p>
        <p className="text-2xl text-slate-600 break-keep">
          잠시 뒤 다시 시도해 주세요. 계속 이러면 직원에게 알려 주세요.
        </p>
        <button
          type="button"
          onClick={reset}
          className="inline-flex cursor-pointer items-center gap-3 rounded-2xl border-4 border-slate-800 bg-white px-8 py-6 text-3xl font-bold text-slate-900 transition-colors duration-200 hover:bg-slate-50"
        >
          <RotateCcw size={32} aria-hidden />
          다시 시도
        </button>
        <p className="pt-4 text-base text-slate-400 break-keep">
          자세한 원인은 브라우저 개발자 도구(F12)의 콘솔에 적혀 있습니다.
        </p>
      </div>
    </main>
  );
}
