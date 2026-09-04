"use client";

import { useEffect, useState } from "react";
import QRCode from "qrcode";

const QR_WIDTH = 320;

/**
 * ATM 연동용 QR (PRD 6.2).
 * QR에는 session_id만 넣는다 — 위험 상세와 개인정보는 ATM이 서버에서 조회한다.
 * 백엔드 왕복 없이 브라우저에서 바로 생성한다(qr-recognition-integration 스킬).
 */
export function QrPanel({ sessionId }: { sessionId: string }) {
  const [dataUrl, setDataUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    QRCode.toDataURL(JSON.stringify({ session_id: sessionId }), {
      width: QR_WIDTH,
      margin: 2,
      errorCorrectionLevel: "M",
    })
      .then((url) => {
        if (!cancelled) setDataUrl(url);
      })
      .catch(() => {
        if (!cancelled) setError("QR 코드를 만들지 못했습니다.");
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  return (
    <div className="flex flex-col items-center gap-4">
      <div className="rounded-2xl border-4 border-slate-900 bg-white p-4">
        {dataUrl ? (
          <img src={dataUrl} alt={`ATM 연동 QR 코드 (${sessionId})`} width={QR_WIDTH} height={QR_WIDTH} />
        ) : (
          <div
            className="flex items-center justify-center bg-slate-100 text-slate-500"
            style={{ width: QR_WIDTH, height: QR_WIDTH }}
          >
            {error ?? "QR 코드를 만드는 중..."}
          </div>
        )}
      </div>
      <p className="font-mono text-lg tracking-wider text-slate-600">{sessionId}</p>
    </div>
  );
}
