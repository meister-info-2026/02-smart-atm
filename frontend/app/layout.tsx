import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "스마트 금융 보안 ATM",
  description: "노약자를 위한 AI 문자 보이스피싱 예방 시스템",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body className="font-sans">{children}</body>
    </html>
  );
}
