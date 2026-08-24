// GET /api/kite-callback?request_token=…  ←  Zerodha redirects here after login.
//
// This is the only place the API secret is used. It exchanges the one-time
// request token for a day-long access token and hands that back to the browser
// in the URL *fragment*.
//
// The fragment is deliberate. Unlike a query string it is never sent to any
// server, never lands in a proxy log, and never appears in a Referer header —
// and the page strips it from the address bar the moment it reads it. The token
// is then held in sessionStorage, so it dies when the tab closes.
//
// Nothing is persisted server-side. There is no endpoint anywhere that will
// hand out your broker token, because the token is never stored to hand out.

import { createHash } from "node:crypto";

export default async (req) => {
  const url = new URL(req.url);
  const requestToken = url.searchParams.get("request_token");
  const status = url.searchParams.get("status");
  const back = (frag) => new Response(null, {
    status: 302,
    headers: { Location: "/" + frag, "Cache-Control": "no-store" },
  });

  if (status === "cancelled") return back("#kite_error=" + encodeURIComponent("Login cancelled"));
  if (!requestToken) return back("#kite_error=" + encodeURIComponent("No request token returned"));

  const key = process.env.KITE_API_KEY, secret = process.env.KITE_API_SECRET;
  if (!key || !secret) {
    return back("#kite_error=" + encodeURIComponent(
      "KITE_API_KEY / KITE_API_SECRET are not set on this site"));
  }

  // Kite's handshake: SHA-256 over api_key + request_token + api_secret.
  const checksum = createHash("sha256").update(key + requestToken + secret).digest("hex");

  try {
    const r = await fetch("https://api.kite.trade/session/token", {
      method: "POST",
      headers: {
        "X-Kite-Version": "3",
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: new URLSearchParams({ api_key: key, request_token: requestToken, checksum }),
    });
    const j = await r.json();
    if (!r.ok || j.status !== "success" || !j.data?.access_token) {
      return back("#kite_error=" + encodeURIComponent(
        j.message || `token exchange failed (http ${r.status})`));
    }
    // Only the access token and the (non-secret) api key travel back.
    return back("#kite=" + encodeURIComponent(j.data.access_token) +
                "&kite_key=" + encodeURIComponent(key) +
                "&kite_user=" + encodeURIComponent(j.data.user_shortname || j.data.user_name || ""));
  } catch (e) {
    return back("#kite_error=" + encodeURIComponent("could not reach api.kite.trade: " + e.message));
  }
};
