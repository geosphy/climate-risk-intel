/** @type {import('next').NextConfig} */

/**
 * BACKEND_URL is a server-side environment variable read at Next.js startup
 * (not baked into the client bundle). Set it to the backend's internal
 * address so the proxy works in every environment:
 *
 *   Local dev:       BACKEND_URL=http://localhost:8000  (default)
 *   Docker Compose:  BACKEND_URL=http://backend:8000
 *   Production:      BACKEND_URL=https://api.yourhost.com
 *
 * Client code uses relative paths (/api/...) which this proxy forwards.
 * No CORS headers are needed because the browser only ever talks to :3000.
 */
const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

const nextConfig = {
  // Prevent ESLint warnings from blocking Vercel builds
  eslint: {
    ignoreDuringBuilds: true,
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${BACKEND_URL}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
