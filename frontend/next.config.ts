import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "sleepercdn.com",
        pathname: "/content/nfl/players/**",
      },
    ],
  },
};

export default nextConfig;
