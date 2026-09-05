"use client";

/**
 * 로그아웃(계정 전환) 버튼.
 *
 * 이 프로젝트는 사용자(halmeoni)와 상담원(callcenter) 두 역할을 오가며 시연한다.
 * 토큰이 브라우저에 남아 있으면 로그인 화면이 다시 뜨지 않아 계정을 바꿀 수 없으므로,
 * 로그인이 필요한 모든 화면에 이 버튼을 둔다.
 */
import { useRouter } from "next/navigation";
import { LogOut } from "lucide-react";
import { clearToken } from "@/lib/api";

export function LogoutButton({ next = "/login" }: { next?: string }) {
  const router = useRouter();

  const logout = () => {
    clearToken();
    router.push(next);
  };

  return (
    <button
      type="button"
      onClick={logout}
      className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition-colors duration-200 hover:bg-slate-100"
    >
      <LogOut size={16} aria-hidden />
      계정 바꾸기
    </button>
  );
}
