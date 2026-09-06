"use client";

import { useEffect, useRef, useState } from "react";
import { readToken } from "@/lib/api";
import type { SocketEvent } from "@/types/api";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000/ws";
const RECONNECT_DELAY_MS = 3000;
const MAX_EVENTS = 20;

/** 서버가 상담원 토큰을 거부했을 때 쓰는 close 코드 (RFC 6455 policy violation) */
const WS_POLICY_VIOLATION = 1008;

/**
 * 백엔드 WebSocket 구독 (자동 재연결).
 * dashboard-ui-design 스킬: 연결이 끊긴 상태를 화면에 반드시 구분해서 표시한다.
 *
 * 이 스트림에는 세션 번호와 위험 등급이 흐르므로 백엔드가 상담원 토큰을 요구한다.
 * 브라우저 WebSocket API는 헤더를 붙일 수 없어 토큰을 쿼리 파라미터로 보낸다.
 */
export function useAtmSocket() {
  const [connected, setConnected] = useState(false);
  const [unauthorized, setUnauthorized] = useState(false);
  const [events, setEvents] = useState<SocketEvent[]>([]);
  const socketRef = useRef<WebSocket | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const closedByUsRef = useRef(false);

  useEffect(() => {
    closedByUsRef.current = false;

    const connect = () => {
      if (closedByUsRef.current) return;

      // 토큰은 화면이 그려진 뒤(localStorage 접근 가능) 매번 새로 읽는다 —
      // 다시 로그인하면 새 토큰으로 붙어야 한다.
      const token = readToken("agent");
      if (!token) {
        setUnauthorized(true);
        return;
      }

      const socket = new WebSocket(`${WS_URL}?token=${encodeURIComponent(token)}`);
      socketRef.current = socket;

      socket.onopen = () => {
        setConnected(true);
        setUnauthorized(false);
      };

      socket.onmessage = (event: MessageEvent<string>) => {
        try {
          const parsed = JSON.parse(event.data) as SocketEvent;
          setEvents((prev) => [parsed, ...prev].slice(0, MAX_EVENTS));
        } catch {
          // 형식이 다른 메시지는 무시한다 (화면을 깨뜨리지 않는다)
        }
      };

      socket.onclose = (event: CloseEvent) => {
        setConnected(false);
        if (event.code === WS_POLICY_VIOLATION) {
          // 토큰이 상담원 것이 아니다. 다시 붙어도 결과가 같으므로 재연결하지 않는다
          // (3초마다 무한히 두드리면 로그만 지저분해진다).
          setUnauthorized(true);
          return;
        }
        if (!closedByUsRef.current) {
          timerRef.current = setTimeout(connect, RECONNECT_DELAY_MS);
        }
      };

      socket.onerror = () => socket.close();
    };

    connect();

    return () => {
      closedByUsRef.current = true;
      if (timerRef.current) clearTimeout(timerRef.current);
      socketRef.current?.close();
    };
  }, []);

  return { connected, unauthorized, events };
}
