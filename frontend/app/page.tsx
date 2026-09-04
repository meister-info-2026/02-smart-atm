import Link from "next/link";
import { Landmark, Headset, MessageSquareText } from "lucide-react";

/**
 * 시작 화면 (PRD 5.1 필수 화면).
 * 노약자용 핵심 행동은 하나 — "문자 검사하기". 나머지 두 화면은 시연/운영용이라
 * 아래쪽에 작게 배치한다 (ui-ux-rules.md: 모든 카드를 같은 크기로 나열하지 않는다).
 */
export default function HomePage() {
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-2xl flex-col justify-center gap-10 px-6 py-12">
      <header className="space-y-3">
        <p className="text-lg font-semibold text-sky-700">스마트 금융 보안 ATM</p>
        <h1 className="text-4xl font-bold leading-snug text-slate-900 break-keep">
          받으신 문자가 안전한지
          <br />
          먼저 확인해 보세요
        </h1>
        <p className="text-xl text-slate-600 break-keep">
          문자 내용을 확인해 보이스피싱 위험을 알려 드립니다.
        </p>
      </header>

      <Link href="/messages" className="btn-primary flex items-center justify-center gap-3">
        <MessageSquareText size={32} aria-hidden />
        문자 검사하기
      </Link>

      <section className="space-y-3 border-t border-slate-200 pt-8">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          시연 · 운영용 화면
        </h2>
        <div className="grid gap-3 sm:grid-cols-2">
          <Link
            href="/atm"
            className="card flex cursor-pointer items-center gap-3 p-4 transition-colors duration-200 hover:bg-slate-100"
          >
            <Landmark className="text-slate-500" size={24} aria-hidden />
            <span className="font-medium text-slate-800">ATM 화면 (7인치)</span>
          </Link>
          <Link
            href="/callcenter"
            className="card flex cursor-pointer items-center gap-3 p-4 transition-colors duration-200 hover:bg-slate-100"
          >
            <Headset className="text-slate-500" size={24} aria-hidden />
            <span className="font-medium text-slate-800">콜센터 상담원 화면</span>
          </Link>
        </div>
      </section>
    </main>
  );
}
