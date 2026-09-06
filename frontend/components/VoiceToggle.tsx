"use client";

import { Volume2, VolumeX } from "lucide-react";
import type { Speech } from "@/hooks/useSpeech";

/**
 * 음성 안내 켜기/끄기 버튼.
 *
 * 전시 준비할 때 한 번 눌러 두는 버튼이다. 지원하지 않는 브라우저에서는
 * 아예 보이지 않는다 — 눌러도 아무 일이 없는 버튼을 남겨 두지 않는다.
 */
export function VoiceToggle({ speech, size = "md" }: { speech: Speech; size?: "md" | "lg" }) {
  if (!speech.supported) return null;

  const big = size === "lg";
  const iconSize = big ? 24 : 18;

  return (
    <button
      type="button"
      onClick={speech.toggle}
      aria-pressed={speech.enabled}
      title={speech.enabled ? "음성 안내를 끕니다" : "안내 문구를 소리로 읽어 줍니다"}
      className={`inline-flex cursor-pointer items-center gap-2 rounded-lg border font-medium transition-colors duration-200 ${
        big ? "px-4 py-3 text-xl" : "px-3 py-2 text-sm"
      } ${
        speech.enabled
          ? "border-sky-600 bg-sky-50 text-sky-800 hover:bg-sky-100"
          : "border-slate-300 bg-white text-slate-600 hover:bg-slate-100"
      }`}
    >
      {speech.enabled ? (
        <Volume2 size={iconSize} aria-hidden />
      ) : (
        <VolumeX size={iconSize} aria-hidden />
      )}
      {speech.enabled ? "음성 안내 켜짐" : "음성 안내 꺼짐"}
    </button>
  );
}
