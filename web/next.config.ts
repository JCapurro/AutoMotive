import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Keep the isolated payment rehearsal separate from the normal dev/build output.
  distDir: process.env.NEXT_DIST_DIR || ".next",
  reactCompiler: true,
  // web/ is the app root inside the monorepo (worker/ and supabase/ live next to it).
  outputFileTracingRoot: __dirname,
};

export default nextConfig;
