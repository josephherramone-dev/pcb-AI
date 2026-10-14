import type { NextConfig } from "next";

// The browser only talks to this Next.js server. API calls under /api are
// proxied to the FastAPI backend, so no backend URL or secret reaches the client.
const backend = process.env.BACKEND_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default nextConfig;
