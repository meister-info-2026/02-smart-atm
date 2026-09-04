import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./hooks/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        // 시스템 기본 산세리프 (ui-ux-rules.md: 외부 폰트 API 호출을 늘리지 않는다)
        sans: [
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Malgun Gothic",
          "Apple SD Gothic Neo",
          "Noto Sans KR",
          "sans-serif",
        ],
      },
    },
  },
  plugins: [],
};

export default config;
