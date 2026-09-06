import path from "path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 显式指定项目根，避免 Next.js 误认上级目录中的历史 package-lock.json
  outputFileTracingRoot: path.join(process.cwd(), ".."),
  // 独立部署模式：产出 .next/standalone，供 Docker 镜像使用
  output: "standalone",
};

export default nextConfig;
