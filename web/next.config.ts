import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactCompiler: true,
  // web/ is the app root inside the monorepo (worker/ and supabase/ live next to it).
  outputFileTracingRoot: __dirname,
};

export default nextConfig;
