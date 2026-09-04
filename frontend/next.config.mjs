/** @type {import('next').NextConfig} */
// dashboard-ui-design 스킬(필수): Strict Mode가 켜져 있으면 개발 모드에서 useEffect가
// 두 번 실행되어 WebSocket 연결이 끊겼다 재연결되는 깜빡임이 생긴다.
const nextConfig = {
  reactStrictMode: false,
};

export default nextConfig;
