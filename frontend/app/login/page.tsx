"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { LogIn } from "lucide-react";
import { ApiError, api, saveToken } from "@/lib/api";
import type { TokenResponse, UserResponse } from "@/types/api";

/** 상담원만 들어갈 수 있는 화면 (backend/security/jwt_auth.py) */
const AGENT_ONLY_PATHS = ["/callcenter"];

/**
 * 로그인 뒤 갈 화면을 정한다.
 *
 * `next`를 그대로 따르면, 콜센터 화면에서 사용자 계정으로 바꿔 로그인했을 때
 * 다시 콜센터로 돌아가 또 권한 오류를 만난다. 그래서 역할이 갈 수 없는 곳이면
 * 역할에 맞는 기본 화면으로 보낸다.
 */
function destinationFor(role: UserResponse["role"], next: string | null): string {
  const home = role === "agent" ? "/callcenter" : "/messages";
  if (!next) return home;
  if (role !== "agent" && AGENT_ONLY_PATHS.some((p) => next.startsWith(p))) return home;
  return next;
}

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const token = await api.post<TokenResponse>("/api/v1/auth/login", {
        username,
        password,
      });
      saveToken(token.access_token);

      // 역할을 확인해 갈 수 있는 화면으로 보낸다. 조회에 실패해도 로그인 자체는
      // 성공했으므로 기본 화면으로 진행한다.
      let role: UserResponse["role"] = "user";
      try {
        role = (await api.get<UserResponse>("/api/v1/users/me")).role;
      } catch {
        role = "user";
      }
      router.push(destinationFor(role, searchParams.get("next")));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "로그인에 실패했습니다.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-md flex-col justify-center gap-8 px-6 py-12">
      <h1 className="text-3xl font-bold text-slate-900">로그인</h1>

      <form onSubmit={submit} className="space-y-5">
        <label className="block space-y-2">
          <span className="text-lg font-medium text-slate-700">아이디</span>
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            required
            className="w-full rounded-xl border-2 border-slate-300 px-4 py-4 text-xl"
          />
        </label>

        <label className="block space-y-2">
          <span className="text-lg font-medium text-slate-700">비밀번호</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
            className="w-full rounded-xl border-2 border-slate-300 px-4 py-4 text-xl"
          />
        </label>

        {error && (
          <p role="alert" className="rounded-xl bg-rose-50 px-4 py-3 text-lg text-rose-800">
            {error}
          </p>
        )}

        <button type="submit" disabled={busy} className="btn-primary flex items-center justify-center gap-3">
          <LogIn size={28} aria-hidden />
          {busy ? "확인 중..." : "로그인"}
        </button>
      </form>

      <p className="text-base text-slate-500 break-keep">
        시연용 계정은 <code className="rounded bg-slate-200 px-1.5 py-0.5">halmeoni</code>(사용자)와{" "}
        <code className="rounded bg-slate-200 px-1.5 py-0.5">callcenter</code>(상담원)입니다. 비밀번호는{" "}
        <code className="rounded bg-slate-200 px-1.5 py-0.5">backend/db/seed.py</code> 실행 시 출력됩니다.
      </p>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<main className="p-6 text-lg">불러오는 중...</main>}>
      <LoginForm />
    </Suspense>
  );
}
