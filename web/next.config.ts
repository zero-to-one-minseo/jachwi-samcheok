import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
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
