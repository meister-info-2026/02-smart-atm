"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

/**
 * 화면의 안내 문구를 소리내어 읽어 준다 (FR-10 노약자 안내).
 *
 * 어르신은 화면보다 소리를 먼저 알아차린다. 큰 글씨만으로는 절반이다.
 * 브라우저에 내장된 음성 합성을 쓰므로 설치할 것도, 인터넷도 필요 없다.
 *
 * 왜 기본이 꺼져 있나:
 *   1) 브라우저는 사람이 화면을 한 번 누르기 전에는 소리를 막는다. 켜는 동작
 *      자체가 그 '한 번 누르기'가 된다.
 *   2) 전시장이 시끄럽거나 옆 부스에 방해가 되면 꺼야 한다. 끌 수 있어야 한다.
 * 한 번 켜 두면 같은 브라우저에서는 계속 켜진 채로 남는다.
 *
 * 왜 이렇게 방어적으로 짰나:
 *   speechSynthesis는 브라우저·기기마다 구현이 제각각이다. 있는 척만 하고
 *   getVoices()에서 예외를 던지거나 addEventListener가 없는 구현이 실제로 있다.
 *   여기서 예외가 새어 나가면 React가 화면 전체를 걷어내 **ATM 화면이 하얗게
 *   빈다.** 이 화면은 전시의 핵심이므로, 음성이 안 되는 것보다 화면이 사라지는
 *   쪽이 훨씬 나쁘다. 그래서 모든 호출을 감싸고, 실패하면 조용히 '지원 안 함'으로
 *   내려앉는다.
 */

const STORAGE_KEY = "smart-atm-voice";
const LANG = "ko-KR";
const RATE = 0.9; // 기본 속도는 어르신이 따라오기에 빠르다
const PITCH = 1;

export interface Speech {
  /** 이 브라우저에서 실제로 소리를 낼 수 있는가 (마운트 후에 정해진다) */
  supported: boolean;
  /** 지금 소리를 낼 것인가 */
  enabled: boolean;
  toggle: () => void;
  /**
   * 안내를 읽는다. 같은 key로 다시 부르면 읽지 않는다 —
   * 화면이 1초마다 폴링하므로 이 검사가 없으면 같은 문장을 끝없이 반복한다.
   */
  announce: (key: string, text: string) => void;
}

/** 음성 합성을 쓸 수 있으면 돌려주고, 조금이라도 이상하면 null. */
function getSynth(): SpeechSynthesis | null {
  try {
    if (typeof window === "undefined") return null;
    if (!("speechSynthesis" in window)) return null;
    if (typeof window.SpeechSynthesisUtterance !== "function") return null;
    const synth = window.speechSynthesis;
    return synth && typeof synth.speak === "function" ? synth : null;
  } catch {
    return null;
  }
}

/** 음성 관련 호출은 전부 이걸 통과시킨다. 실패해도 화면은 살아 있어야 한다. */
function attempt(action: () => void): boolean {
  try {
    action();
    return true;
  } catch {
    return false;
  }
}

function readStored(): boolean {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === "on";
  } catch {
    return false; // 시크릿 창 등에서 접근이 막힐 수 있다
  }
}

function writeStored(on: boolean): void {
  // 저장하지 못해도 이번 세션 동안은 동작한다
  attempt(() => window.localStorage.setItem(STORAGE_KEY, on ? "on" : "off"));
}

export function useSpeech(): Speech {
  const [supported, setSupported] = useState(false);
  const [enabled, setEnabled] = useState(false);
  const spokenKeyRef = useRef<string | null>(null);
  const voiceRef = useRef<SpeechSynthesisVoice | null>(null);

  // localStorage와 speechSynthesis는 브라우저에만 있다 — 그려진 뒤에 확인한다
  // (서버에서 그린 화면과 어긋나지 않게).
  useEffect(() => {
    const synth = getSynth();
    if (!synth) return;

    const pickVoice = () => {
      // getVoices()에서 예외를 던지는 구현이 있다. 목소리를 못 고르면
      // 기본 목소리로 읽으면 되므로 실패해도 그냥 넘어간다.
      attempt(() => {
        const voices = synth.getVoices();
        voiceRef.current =
          voices?.find((v) => v.lang?.toLowerCase().startsWith("ko")) ?? null;
      });
    };
    pickVoice();

    // 목록이 비어 있다가 나중에 채워지는 브라우저가 있다.
    // 반대로 addEventListener 자체가 없는 구현도 있다 — 있을 때만 붙인다.
    const canListen = typeof synth.addEventListener === "function";
    if (canListen) attempt(() => synth.addEventListener("voiceschanged", pickVoice));

    // 여기까지 왔으면 최소한 화면을 깨뜨리지 않고 쓸 수 있다
    setSupported(true);
    setEnabled(readStored());

    return () => {
      if (canListen) attempt(() => synth.removeEventListener("voiceschanged", pickVoice));
      attempt(() => synth.cancel());
    };
  }, []);

  const speak = useCallback((text: string) => {
    const said = text.trim();
    if (!said) return;
    const synth = getSynth();
    if (!synth) return;

    attempt(() => {
      // 앞 문장이 남아 있으면 끊는다 — 상태가 바뀌었는데 지난 안내를 계속 읽으면 안 된다
      synth.cancel();
      const utterance = new window.SpeechSynthesisUtterance(said);
      utterance.lang = LANG;
      utterance.rate = RATE;
      utterance.pitch = PITCH;
      if (voiceRef.current) utterance.voice = voiceRef.current;
      synth.speak(utterance);
    });
  }, []);

  const announce = useCallback(
    (key: string, text: string) => {
      // 꺼져 있어도 key는 기억해 둔다. 그래야 나중에 켰을 때 이미 지나간
      // 안내를 뒤늦게 쏟아내지 않는다.
      const isNew = spokenKeyRef.current !== key;
      spokenKeyRef.current = key;
      if (!isNew || !supported || !enabled) return;
      speak(text);
    },
    [enabled, supported, speak],
  );

  const toggle = useCallback(() => {
    setEnabled((prev) => {
      const next = !prev;
      writeStored(next);
      if (next) {
        // 켜는 순간 '지금 화면에 떠 있는 안내'를 다시 읽게 한다.
        // 기억해 둔 key를 지우면 화면 쪽 effect가 곧바로 다시 읽어 준다 —
        // "켰습니다" 같은 빈 확인음보다, 실제로 필요한 문장을 듣는 편이 낫다.
        // (켜는 조작 자체가 브라우저가 요구하는 '사람의 조작'을 만족시킨다)
        spokenKeyRef.current = null;
      } else {
        attempt(() => getSynth()?.cancel());
      }
      return next;
    });
  }, []);

  // 매 렌더마다 새 객체를 돌려주면, 이걸 의존성으로 쓰는 쪽의 effect가 계속 다시 돈다
  return useMemo(
    () => ({ supported, enabled, toggle, announce }),
    [supported, enabled, toggle, announce],
  );
}
