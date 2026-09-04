"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ChevronRight, Inbox, PencilLine, Search } from "lucide-react";
import { ApiError, api, readToken } from "@/lib/api";
import type { AnalysisResponse, ChatRoomResponse, MessageResponse } from "@/types/api";

type Mode = "select" | "type";

/**
 * 문자 입력/선택 화면 (PRD 5.1 / FR-01).
 * 노약자 UI 원칙: 한 화면에 하나의 핵심 행동 — "보이스피싱 검사하기".
 */
export default function MessagesPage() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("select");
  const [chats, setChats] = useState<ChatRoomResponse[]>([]);
  const [openChatId, setOpenChatId] = useState<number | null>(null);
  const [messages, setMessages] = useState<MessageResponse[]>([]);
  const [selectedMessageId, setSelectedMessageId] = useState<number | null>(null);
  const [typed, setTyped] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const handleError = useCallback(
    (err: unknown) => {
      if (err instanceof ApiError && err.status === 401) {
        router.push("/login?next=/messages");
        return;
      }
      setError(err instanceof ApiError ? err.message : "문제가 생겼습니다. 다시 시도해 주세요.");
    },
    [router],
  );

  useEffect(() => {
    if (!readToken()) {
      router.push("/login?next=/messages");
      return;
    }
    api
      .get<ChatRoomResponse[]>("/api/v1/chats")
      .then(setChats)
      .catch(handleError);
  }, [router, handleError]);

  const openChat = async (chatId: number) => {
    setOpenChatId(chatId);
    setSelectedMessageId(null);
    setError(null);
    try {
      setMessages(await api.get<MessageResponse[]>(`/api/v1/chats/${chatId}/messages`));
    } catch (err) {
      handleError(err);
    }
  };

  const analyze = async () => {
    setBusy(true);
    setError(null);
    try {
      const result =
        mode === "type"
          ? await api.post<AnalysisResponse>("/api/v1/analysis", { message: typed })
          : await api.post<AnalysisResponse>(`/api/v1/analysis/chats/${openChatId}`, {
              message_id: selectedMessageId,
            });
      router.push(`/result/${result.analysis_id}`);
    } catch (err) {
      handleError(err);
      setBusy(false);
    }
  };

  const canAnalyze =
    mode === "type" ? typed.trim().length > 0 : selectedMessageId !== null;

  return (
    <main className="mx-auto w-full max-w-2xl space-y-8 px-6 py-10">
      <header className="space-y-2">
        <h1 className="text-3xl font-bold text-slate-900">검사할 문자를 고르세요</h1>
        <p className="text-lg text-slate-600 break-keep">
          받은 문자를 목록에서 고르거나, 직접 입력할 수 있습니다.
        </p>
      </header>

      <div role="tablist" className="grid grid-cols-2 gap-2 rounded-xl bg-slate-200 p-1.5">
        <TabButton active={mode === "select"} onClick={() => setMode("select")} Icon={Inbox}>
          받은 문자에서 고르기
        </TabButton>
        <TabButton active={mode === "type"} onClick={() => setMode("type")} Icon={PencilLine}>
          직접 입력하기
        </TabButton>
      </div>

      {mode === "select" ? (
        <section className="space-y-3">
          {chats.length === 0 && <p className="text-lg text-slate-500">받은 문자가 없습니다.</p>}

          {chats.map((chat) => (
            <div key={chat.id} className="card overflow-hidden">
              <button
                type="button"
                onClick={() => (openChatId === chat.id ? setOpenChatId(null) : openChat(chat.id))}
                className="flex w-full cursor-pointer items-center justify-between gap-3 p-5 text-left transition-colors duration-200 hover:bg-slate-50"
              >
                <span className="min-w-0">
                  <span className="block truncate text-lg font-semibold text-slate-900">
                    {chat.title}
                  </span>
                  <span className="mt-1 block truncate text-base text-slate-500">
                    {chat.last_message ?? "내용 없음"}
                  </span>
                </span>
                <ChevronRight
                  className={`shrink-0 text-slate-400 transition-transform duration-200 ${
                    openChatId === chat.id ? "rotate-90" : ""
                  }`}
                  size={24}
                  aria-hidden
                />
              </button>

              {openChatId === chat.id && (
                <ul className="space-y-2 border-t border-slate-200 bg-slate-50 p-4">
                  {messages.map((message) => (
                    <li key={message.id}>
                      <button
                        type="button"
                        onClick={() => setSelectedMessageId(message.id)}
                        className={`w-full cursor-pointer rounded-xl border-2 p-4 text-left text-lg leading-relaxed transition-colors duration-200 break-keep ${
                          selectedMessageId === message.id
                            ? "border-sky-600 bg-sky-50 text-slate-900"
                            : "border-slate-200 bg-white text-slate-700 hover:bg-slate-100"
                        }`}
                      >
                        <span className="mb-1 block text-sm font-semibold text-slate-500">
                          {message.sender_label}
                        </span>
                        {message.content}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </section>
      ) : (
        <section className="space-y-3">
          <label htmlFor="typed-message" className="block text-lg font-medium text-slate-700">
            받은 문자 내용을 그대로 적어 주세요
          </label>
          <textarea
            id="typed-message"
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            rows={7}
            placeholder="예) 검찰입니다. 계좌가 범죄에 연루되었습니다..."
            className="w-full rounded-xl border-2 border-slate-300 p-4 text-xl leading-relaxed"
          />
        </section>
      )}

      {error && (
        <p role="alert" className="rounded-xl bg-rose-50 px-4 py-3 text-lg text-rose-800">
          {error}
        </p>
      )}

      <button
        type="button"
        onClick={analyze}
        disabled={!canAnalyze || busy}
        className="btn-primary sticky bottom-4 flex items-center justify-center gap-3"
      >
        <Search size={32} aria-hidden />
        {busy ? "검사하는 중..." : "보이스피싱 검사하기"}
      </button>
    </main>
  );
}

function TabButton({
  active,
  onClick,
  Icon,
  children,
}: {
  active: boolean;
  onClick: () => void;
  Icon: typeof Inbox;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={`flex cursor-pointer items-center justify-center gap-2 rounded-lg px-3 py-3 text-base font-semibold transition-colors duration-200 ${
        active ? "bg-white text-sky-800 shadow-sm" : "text-slate-600 hover:text-slate-900"
      }`}
    >
      <Icon size={20} aria-hidden />
      {children}
    </button>
  );
}
