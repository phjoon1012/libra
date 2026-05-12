/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  transpilePackages: ["@libra/shared-types", "@libra/prompts"],
  typedRoutes: true,
};

export default nextConfig;
