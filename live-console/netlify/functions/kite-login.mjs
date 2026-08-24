// GET /api/kite-login  →  302 to Zerodha's login page.
//
// Kite issues an access token that is valid until roughly 07:30 IST the next
// morning, so this is a once-a-day click, not a stored credential. The API
// secret never appears here — it is only used server-side in kite-callback.

export default async () => {
  const key = process.env.KITE_API_KEY;
  if (!key) {
    return new Response(
      "KITE_API_KEY is not set on this site. Add it under Site configuration → " +
      "Environment variables, along with KITE_API_SECRET, then try again.",
      { status: 503, headers: { "Content-Type": "text/plain" } });
  }
  return new Response(null, {
    status: 302,
    headers: {
      Location: `https://kite.zerodha.com/connect/login?v=3&api_key=${encodeURIComponent(key)}`,
      "Cache-Control": "no-store",
    },
  });
};
