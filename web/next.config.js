/** @type {import('next').NextConfig} */
const nextConfig = {
  // Static export for bundling with FastAPI server
  output: 'export',

  // Disable image optimization (not available in static export)
  images: {
    unoptimized: true,
  },

  // Trailing slashes for proper static file routing
  trailingSlash: true,
}

module.exports = nextConfig
