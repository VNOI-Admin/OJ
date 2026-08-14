// websocket/config.js template for the Dockerized deployment.
//
// websocket/config.js itself is gitignored (see .gitignore) because in the
// native deployment it's generated per-server by vnoi_setup.sh alongside
// dmoj/local_settings.py. For the Docker image, these values are static
// (they're internal container ports, not secrets, and don't vary between
// environments the way DB/SMTP credentials do), so this checked-in template
// is copied to websocket/config.js at image build time (see Dockerfile).
//
// Matches thinkcode-deploy/docker-compose.production.yml's wsevent service
// (network_mode: host, ports 15100/15101/15102) and nginx/vnoj.conf.docker's
// /event/ and /channels/ proxy_pass targets.
const config = {
  get_host: '127.0.0.1',
  get_port: 15100,
  post_host: '127.0.0.1',
  post_port: 15101,
  http_host: '127.0.0.1',
  http_port: 15102,
  long_poll_timeout: 29000,
};

export default config;
