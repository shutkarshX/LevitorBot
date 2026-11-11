# TeraBox resolver modes

Snapit supports an ordered resolver chain. Configure it with environment variables;
do not put cookies or private resolver URLs in source control.

## Modes

- `native`: requests the public share page and TeraBox public share metadata endpoints.
  It returns a watch or download URL only when TeraBox actually supplies enough data.
- `external`: optional HTTPS JSON endpoint configured by the administrator. This
  sends the share URL to that endpoint, so enable it only when its operator is trusted.
- `cookie`: optional user-configured `ndus` cookie for TeraBox endpoints that require
  an authenticated session. The cookie is never logged or returned to users.

## Environment

```dotenv
TERABOX_RESOLVER_ORDER=native,external,cookie
TERABOX_EXTERNAL_RESOLVER_URL=
TERABOX_NDUS_COOKIE=
```

The default is `native` only. External and cookie modes are opt-in. Resolver order
is significant: Snapit stops at the first method that returns at least one usable
watch or download URL.

The external endpoint must accept a JSON POST body `{"url":"<share-url>"}` and
return JSON with `filename`, `size`, and at least one of `watch_url` /
`stream_url` or `download_url` / `direct_link`.

## Current integration status

This commit adds the resolver module and isolated unit tests. The existing Telegram
message handler still uses the prior public-share inspection flow; wiring the
resolver results into Telegram Watch / Download buttons is a separate integration
step. No production bot, database, or deployment is changed by this module.
