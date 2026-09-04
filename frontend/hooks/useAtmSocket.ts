"use client";

import { useEffect, useRef, useState } from "react";
import type { SocketEvent } from "@/types/api";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000/ws";
const RECONNECT_DELAY_MS = 3000;
const MAX_EVENTS = 20;

/**
 * 백엔드 WebSocket 구독 (자동 재연결).
 * dashboard-ui-design 스킬: 연결이 끊긴 상태를 화면에 반드시 구분해서 표시한다.
 */
export function useAtmSocket() {
  const [connected, setConnected] = useState(false);
  const [events, setEvents] = useState<SocketEvent[]>([]);
  const socketRef = useRef<WebSocket | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const closedByUsRef = useRef(false);

  useEffect(() => {
    closedByUsRef.current = false;

    const connect = () => {
      if (closedByUsRef.current) return;

      const socket = new WebSocket(WS_URL);
      socketRef.current = socket;

      socket.onopen = () => setConnected(true);

      socket.onmessage = (event: MessageEvent<string>) => {
        try {
          const parsed = JSON.parse(event.data) as SocketEvent;
          setEvents((prev) => [parsed, ...prev].slice(0, MAX_EVENTS));
        } catch {
          // 형식이 다른 메시지는 무시한다 (화면을 깨뜨리지 않는다)
        }
      };

      socket.onclose = () => {
        setConnected(false);
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

  return { connected, events };
}
