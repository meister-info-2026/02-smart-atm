"use client";

/**
 * 역할별 로그아웃 버튼.
 *
 * 이 앱은 사용자(어르신) 화면과 상담원 화면을 한 PC에서 동시에 띄워 시연한다.
 * 로그인 정보를 역할마다 따로 두므로, 이 버튼은 **자기 역할만** 로그아웃한다 —
 * 상담원 창에서 로그아웃해도 사용자 창의 로그인은 그대로 남는다.
 */
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { LogOut } from "lucide-react";
import { clearToken, readDisplayName, type Role } from "@/lib/api";

export function LogoutButton({ role, next }: { role: Role; next: string }) {
  const router = useRouter();
  const [name, setName] = useState<string | null>(null);

  // localStorage는 브라우저에만 있으므로 화면이 그려진 뒤에 읽는다.
  useEffect(() => setName(readDisplayName(role)), [role]);

  const logout = () => {
    clearToken(role);
    router.push(next);
  };

  return (
    <div className="flex items-center gap-2">
      {name && (
        <span className="text-sm text-slate-500" title={role === "agent" ? "상담원" : "사용자"}>
          {name}
        </span>
      )}
      <button
        type="button"
        onClick={logout}
        className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition-colors duration-200 hover:bg-slate-100"
      >
        <LogOut size={16} aria-hidden />
        로그아웃
      </button>
    </div>
  );
}
