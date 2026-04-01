/** @type {import('next').NextConfig} */
const nextConfig = {
  // Allow the frontend to call the backend API in Docker
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
