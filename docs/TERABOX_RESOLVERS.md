# TeraBox resolver methods

Snapit lets each Telegram user choose how their TeraBox links are resolved.
The selection is stored in the bot's SQLite database and reused for future
links. Users can change it at any time with `/terabox`.

## User-facing methods

- **External scraper**: calls the administrator-configured HTTPS JSON resolver.
  The share URL is sent to that service, so configure only a trusted endpoint.
- **Our own scraper**: uses Snapit's native public-share resolver. If an
  administrator has configured an `ndus` cookie, the cookie-assisted resolver
  is attempted after the native resolver fails.

On the first TeraBox link, Snapit asks the user to choose. Once selected,
subsequent links are processed immediately using that preference. The result
contains Watch and/or Download buttons only when a resolver returns usable
direct URLs. Snapit does not silently fall back to the original TeraBox page.

## Environment

```dotenv
TERABOX_EXTERNAL_RESOLVER_URL=
TERABOX_NDUS_COOKIE=
```

The external endpoint must accept an HTTPS JSON POST body containing
`{"url":"<TeraBox share URL>"}` and return JSON with a usable watch and/or
download URL. Supported response keys include `watch_url` or `stream_url`,
and `download_url` or `direct_link`; `filename` and `size` are optional.

The external method is not available until a trusted endpoint is configured.
The own-scraper method may still fail for shares where TeraBox requires
authorization or changes its private API. A successful metadata lookup is not
proof that a direct playback or download URL was generated.

## Security and operation

- Keep `TERABOX_NDUS_COOKIE` server-side in the host's environment; never
  commit it or send it in Telegram.
- Treat the external resolver as a recipient of the full share URL.
- Resolver failures are reported as failures. Snapit does not send the
  original ad-filled share page as a fake direct link.
- Existing channel records and category assignments are not rebuilt by the
  preference-table migration.
