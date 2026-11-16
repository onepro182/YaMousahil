const http = require('http');
const fs = require('fs');
const path = require('path');
const server = http.createServer((req, res) => {
  try {
    const fp = req.url === '/' ? 'index.html' : decodeURIComponent(req.url);
    const full = path.resolve('C:/Users/Admin/Desktop/APK/APP_web/' + fp.replace(/^\//, ''));
    fs.readFile(full, (err, data) => {
      if (err) { res.writeHead(404); res.end('404'); return; }
      // Anti-cache : le navigateur doit toujours charger la dernière version (mêmes règles que l'APK Android)
      res.writeHead(200, {
        'Content-Type': 'text/html; charset=utf-8',
        'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
        'Pragma': 'no-cache',
        'Expires': '0'
      });
      res.end(data);
    });
  } catch (e) { res.writeHead(500); res.end(String(e)); }
});
server.listen(8765, '127.0.0.1', () => console.log('Server http://localhost:8765'));
