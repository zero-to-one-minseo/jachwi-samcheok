import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  // 노트북 개발 때 /api를 넘겨줄 때 기본 30초에서 끊긴다. 실제 계약서 분석은 50초 가까이 걸려 5분으로 늘린다.
  experimental: { proxyTimeout: 300_000 },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  // 배포(Vercel)에서는 api/analyze.py가 /api/analyze를 바로 받는다.
  // 노트북 개발 때만 api/_dev_server.py(127.0.0.1:8822)로 넘긴다.
  async rewrites() {
    if (process.env.NODE_ENV !== "development") return [];
    return [{ source: "/api/:path*", destination: "http://127.0.0.1:8822/api/:path*" }];
  },
};

export default nextConfig;
