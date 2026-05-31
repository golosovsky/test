const http = require("http");
const fs = require("fs");
const path = require("path");
const url = require("url");

const PORT = process.env.PORT || 3000;

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".css":  "text/css",
  ".js":   "application/javascript",
  ".json": "application/json",
  ".png":  "image/png",
  ".svg":  "image/svg+xml",
  ".ico":  "image/x-icon",
};

const server = http.createServer((req, res) => {
  const parsed = url.parse(req.url);
  let filePath = parsed.pathname === "/" ? "/index.html" : parsed.pathname;
  filePath = path.join(__dirname, filePath);

  const ext = path.extname(filePath);
  const contentType = MIME[ext] || "text/plain";

  fs.readFile(filePath, (err, data) => {
    if (err) {
      res.writeHead(err.code === "ENOENT" ? 404 : 500);
      res.end(err.code === "ENOENT" ? "Not found" : "Server error");
      return;
    }
    res.writeHead(200, { "Content-Type": contentType });
    res.end(data);
  });
});

server.listen(PORT, () => {
  console.log(`Netanya Surf Conditions running at http://localhost:${PORT}`);
});
