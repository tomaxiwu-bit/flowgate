import path from "path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 显式指定项目根，避免 Next.js 误认上级目录中的历史 package-lock.json
  outputFileTracingRoot: path.join(process.cwd(), ".."),
  // 独立部署模式：产出 .next/standalone，供 Docker 镜像使用
  output: "standalone",
  // /api/* 代理到后端。NEXT_PUBLIC_API_BASE_URL 在构建时注入（Docker/远程部署）；
  // 本地开发默认 127.0.0.1:8000。
  async rewrites() {
    const backend = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${backend}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
