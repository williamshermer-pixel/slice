import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // zarrita reaches for `numcodecs/*` via dynamic import. Nothing to configure
  // for the volumes we ship — they are stored uncompressed — but leaving the
  // dependency resolvable keeps compressed volumes working if one appears.
  reactStrictMode: true,
};

export default nextConfig;
