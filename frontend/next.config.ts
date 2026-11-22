import path from "path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 显式指定项目根，避免 Next.js 误认上级目录中的历史 package-lock.json
  outputFileTracingRoot: path.join(process.cwd(), ".."),
  // 独立部署模式：产出 .next/standalone，供 Docker 镜像使用
  output: "standalone",
  // rewrite 代理默认只放行 10MB 请求体，FCS 常超过；放开到 500MB 与后端上限一致。
  experimental: {
    middlewareClientMaxBodySize: "500mb",
  },
  // /api/* 代理到后端。NEXT_PUBLIC_API_BASE_URL 在构建时注入（Docker/远程部署）；
  // 本地开发默认 127.0.0.1:8000。
  async rewrites() {
    const backend = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${backend}/api/:path*`,
      },
      // API 文档页也走同源，避免部署后仍指向 127.0.0.1
      { source: "/docs", destination: `${backend}/docs` },
      { source: "/openapi.json", destination: `${backend}/openapi.json` },
    ];
  },
};

export default nextConfig;
