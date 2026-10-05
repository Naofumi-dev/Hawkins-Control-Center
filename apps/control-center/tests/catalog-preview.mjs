// Isolated local UI fixture. No credentials, external requests, or business writes.
// This file is not imported by the production app and is not copied into Docker.
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { resolve, extname } from "node:path";
import { fileURLToPath } from "node:url";
import { acquisitionResponse } from "./acquisition-fixtures.mjs";
import {
  fixtureOwner,
  emptyWorkspaceFixture,
  catalogResponse,
} from "./catalog-fixtures.mjs";
const root = fileURLToPath(new URL("../dist/", import.meta.url));
const shim = `const realFetch = window.fetch.bind(window); window.fetch = (input, init) => { const u = new URL(input, location.href); if (u.origin === 'https://mtdavgadkiiofwikzdtn.supabase.co' && u.pathname === '/auth/v1/token') return realFetch('/__fixture/auth', init); if (u.origin !== location.origin) return Promise.reject(new Error('External requests disabled in UI fixture')); return realFetch(input, init); };`;
const server = createServer(async (req, res) => {
  const url = new URL(req.url, "http://127.0.0.1:8090");
  const json = (value, status = 200) => {
    res.writeHead(status, {
      "Content-Type": "application/json",
      "Cache-Control": "no-store",
    });
    res.end(JSON.stringify(value));
  };
  try {
    if (url.pathname === "/__fixture/auth")
      return json({
        access_token: "synthetic-token",
        refresh_token: "synthetic-refresh",
        expires_in: 3600,
        user: { email: fixtureOwner },
      });
    if (url.pathname === "/api/config")
      return json({
        owner_email: fixtureOwner,
        supabase_url: "https://mtdavgadkiiofwikzdtn.supabase.co",
        publishable_key: "synthetic-public",
        configured: true,
      });
    if (url.pathname.startsWith("/api/")) {
      if (req.headers.authorization === "Bearer synthetic-token" && url.pathname.startsWith("/api/acquisition")) {
        let body="";
        for await (const chunk of req) { body+=chunk; if(body.length>100000) return json({error:"Fixture body too large"},400); }
        return json(acquisitionResponse(url,req.method,body?JSON.parse(body):{}));
      }
      if (req.method !== "GET")
        return json({ error: "Fixture is read only" }, 405);
      if (req.headers.authorization !== "Bearer synthetic-token")
        return json({ error: "Fixture sign in required" }, 403);
      if (url.pathname === "/api/workspace") return json(emptyWorkspaceFixture);
      const value = catalogResponse(url);
      return json(
        value || { error: "Unknown fixture route" },
        value ? 200 : 404,
      );
    }
    if (url.pathname === "/__fixture/shim.js") {
      res.writeHead(200, { "Content-Type": "text/javascript" });
      return res.end(shim);
    }
    const path = resolve(
      root,
      "." +
        decodeURIComponent(url.pathname === "/" ? "/index.html" : url.pathname),
    );
    if (!path.startsWith(root)) {
      res.writeHead(404);
      return res.end();
    }
    let body = await readFile(path);
    if (path.endsWith("index.html"))
      body = Buffer.from(
        body
          .toString()
          .replace("<head>", '<head><script src="/__fixture/shim.js"></script>')
          .replace("<title>", "<title>TEST FIXTURE · "),
      );
    res.writeHead(200, {
      "Content-Type":
        {
          ".html": "text/html",
          ".js": "text/javascript",
          ".css": "text/css",
          ".woff2": "font/woff2",
          ".woff": "font/woff",
        }[extname(path)] || "application/octet-stream",
      "Cache-Control": "no-store",
      "Content-Security-Policy":
        "default-src 'self'; connect-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'",
    });
    res.end(body);
  } catch {
    json({ error: "Fixture unavailable" }, 404);
  }
});
server.listen(8090, "127.0.0.1", () =>
  process.stdout.write(
    "Synthetic UI fixture at http://127.0.0.1:8090 (any test password)\n",
  ),
);
