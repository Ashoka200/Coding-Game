# Connecting Zerodha

Two things to set up once, then it is one click each morning.

## 1. Get a Kite Connect app

1. Sign in at <https://developers.kite.trade/> with your Zerodha account.
2. Create an app. Kite Connect costs **₹500/month** per app.
3. Set the **Redirect URL** to exactly:

   ```
   https://<your-site>.netlify.app/api/kite-callback
   ```

   It must match character for character or Zerodha refuses the login.
4. Copy the **API key** and **API secret**.

## 2. Put the secret on the site, not in the browser

In Netlify → Site configuration → Environment variables, add:

| Variable | Value |
|---|---|
| `KITE_API_KEY` | your API key |
| `KITE_API_SECRET` | your API secret |

Redeploy so the functions pick them up.

The secret is used in exactly one place — `kite-callback.mjs`, server-side, to
sign the token exchange. It is never sent to the browser, and a test asserts
that it appears nowhere in client code.

## 3. Each morning

Click **Connect Zerodha** in the masthead. You log in on Zerodha's own page —
this site never sees your password or your PIN. The button turns green and
reads *Zerodha live*; the tape switches from `Live · <clock>` to
`Streaming · every tick`.

Kite invalidates the access token around **07:30 IST daily**, by design. When
it expires the button says *Session ended — reconnect*.

## What happens to the token

- Returned in the URL **fragment**, which is never sent to any server, never
  logged by a proxy, and never appears in a `Referer` header.
- Stripped from the address bar the instant it is read.
- Held in `sessionStorage`, so it dies when you close the tab.
- **Never written to the server.** There is no endpoint that will hand out your
  broker token, because it is never stored anywhere to hand out.

## What this deliberately does not do

The Kite access token can place orders. That is precisely why the streaming
client will not: it subscribes to market data and does nothing else. There is
no order path in `kite.js`, and a test fails the build if one appears.

Order placement stays as it was — a basket handed to Kite, confirmed by you,
inside Zerodha's own app, with your own PIN.

## If it will not connect

The button's tooltip carries the reason. The usual causes:

| Message | Cause |
|---|---|
| `KITE_API_KEY is not set` | environment variables missing, or not redeployed |
| `Invalid checksum` | `KITE_API_SECRET` does not match the key |
| `no instrument tokens resolved` | `api.kite.trade` unreachable from the function |
| `Session ended — reconnect` | the daily expiry, or a login elsewhere |

Without a connection nothing breaks: the tape falls back to polling NSE and BSE
every five seconds, exactly as before.
