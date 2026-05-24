/** @type {import('next').NextConfig} */
const nextConfig = {
  // Proxy /api/* to the DataMingler Python server so the browser
  // never makes a cross-origin request.
  async rewrites() {
    const pythonApi = process.env.PYTHON_API_URL ?? 'http://localhost:8080';
    return [
      {
        source: '/api/:path*',
        destination: `${pythonApi}/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
