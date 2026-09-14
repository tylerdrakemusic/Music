# Pandora Official Integration Feasibility Spike

**FR:** `FR-20260913-pandora-official-integration-spike`  
**Related TODO:** 654  
**Parent TODO:** 651  
**Downstream TODO:** 655, single-user local Pandora authentication and provider adapter  
**Research date:** 2026-09-13  
**Scope:** Official Pandora developer/API products, embeds or handoff, OAuth, playback, control rights, and subscription constraints. No credentials, tokens, unofficial APIs, or scraping were used.

## Decision

**Conditional GO for a future partner-approved in-portal adapter; NO-GO for implementation now.**

Pandora's current official developer center documents a partner-gated GraphQL API that can search the catalog, list listener collections, create or retrieve stations, return audio URLs, and perform playback and feedback operations. The official sample web app demonstrates an in-browser playback component using an HTML5-style audio player and GraphQL mutations. This is technically aligned with the requested portal workflow.

The gate is material: Pandora partnership access must be requested and approved before developer portal access, API Explorer use, application creation, and client credentials are available. The current public documentation does not establish that this project has partner approval, a registered application, a published application, an approved redirect URI, or the required subscription/account entitlements. The public docs also describe the GraphQL client/sample web app, not a separately documented iframe/embed SDK or a public no-auth handoff-control contract.

Therefore, TODO 655 must remain blocked pending a human-owned partner-access decision and application/contract confirmation. If access is approved, the strongest supported workflow is a local single-user OAuth client with server-side token exchange and protected refresh-token storage, Pandora GraphQL for station/playback state and controls, and a local audio element for playback. If access is not approved, the only low-risk fallback in scope is an official Pandora destination link, which is a handoff and cannot provide the requested in-portal controls.

## 1. Official products and current availability

| Product or surface | Official evidence | Availability and implication |
| --- | --- | --- |
| Pandora Developer Center | [Developer Center](https://developer.pandora.com/) | Live public portal as checked on 2026-09-13. It advertises partner applications powered by GraphQL and a join flow. Public visibility is not public API availability. |
| Pandora GraphQL API | [GraphQL reference](https://developer.pandora.com/docs/reference/graphql/) | Partner API. It covers search, collections, profile, feedback, listener resources, and playback. |
| Partner portal, API Explorer, sample web app | [Support and API Features](https://developer.pandora.com/docs/overview/support-and-api-features/) and [Partner Access](https://developer.pandora.com/docs/overview/partner-access/) | Requires partner registration/approval. Approved partners get application management, API Explorer, documentation, and sample app access. |
| AMP | [AMP destination](https://amp.pandora.com/) | The historical AMP URL redirects to `ampplaybook.com` in the current check. AMP is an artist/marketing destination, not evidence of a listener playback API or portal embed contract. The existing artist-profile AMP link should not be treated as an integration endpoint. |

The partner request form asks for company and project information, including distribution method, target audience, projected sales, and launch date: [Becoming a Pandora Partner](https://developer.pandora.com/docs/getting-started/becoming-pandora-partner/). This is a business approval gate, not self-service API signup.

## 2. Embed, destination, and browser boundary

### Official in-portal playback

Pandora's official sample web app shows a browser client using a playback component and an `AudioPlayer` component. The documented flow obtains an audio URL and track metadata from GraphQL, then sends start, progress, end, pause, play, skip, and feedback events back to Pandora. See [Playback with Pandora](https://developer.pandora.com/docs/tutorials/playback-pandora/) and [Playback component](https://developer.pandora.com/docs/tutorials/station-playback/playback-component/).

This is an official API-mediated browser playback model, not a Pandora-hosted iframe that can be dropped into the portal. The public developer navigation and docs reviewed for this spike expose the GraphQL API, API Explorer, and sample web app; they do not publish a separate iframe/embed SDK, embed URL contract, browser postMessage control API, or unauthenticated web-player embed. Do not infer those capabilities from ordinary `pandora.com` pages or AMP.

### Official handoff

A normal Pandora destination, such as the artist URL already recorded in `ARTIST_PROFILE.json`, can be used as a user-facing handoff only. Pandora's developer docs do not document a handoff URL that accepts station selection, shuffle, play/pause, skip, or thumbs-up commands from the Music portal. A handoff therefore leaves playback and control in Pandora's destination and cannot satisfy the in-portal MVP controls by itself.

### Browser and local-development implications

- The authorization-code documentation explicitly describes a web client and shows a `localhost:3000/oauth/callback` example in the tutorial: [Authentication and Authorization tutorial](https://developer.pandora.com/docs/tutorials/authenticate-app-user-pandora/authentication-authorization/).
- The callback must use the redirect URI registered for the application and the token exchange must use the same redirect URI: [Authorization Code Grant](https://developer.pandora.com/docs/reference/graphql-api/authentication-using-oauth2/authorization-code-grant/).
- PKCE is recommended for public clients; the documented token exchange also requires HTTP Basic authentication with `client_id:client_secret`. Consequently, a browser-only public client must not receive the client secret. A local server-side callback/token exchange is the safer shape for TODO 655, subject to Pandora approving the local redirect URI.
- The docs do not publish a browser iframe policy or CORS/postMessage contract for an embed. The implementation must not rely on cross-origin iframe control, scraped page audio, undocumented endpoints, or browser automation.
- Audio URLs are short-lived: up to one hour for radio stations and about five minutes for on-demand tracks. They must be fetched just in time and refreshed when expired: [Things Every Developer Should Know](https://developer.pandora.com/docs/reference/graphql-api/overview/things-every-developer-should-know/).

## 3. OAuth, entitlement, and credential requirements

| Requirement | Official finding | Consequence |
| --- | --- | --- |
| Grant | Authorization Code Grant is documented for a web client. Authorization endpoint: `https://www.pandora.com/oauth/v1/authorize`; token endpoint: `https://www.pandora.com/oauth/v1/token`. | Use user consent; never collect or store a Pandora password. |
| Client ID/secret | Pandora generates a client ID and client secret when a partner creates an application: [Applications](https://developer.pandora.com/docs/key-concepts/applications/). | Application creation is unavailable until partner access. Keep the secret server-side and out of source/runtime data committed to the repo. |
| PKCE | `code_challenge_method=S256` is the only permitted method when PKCE is used; PKCE is highly recommended for public clients. | Generate a verifier per authorization attempt and keep it transient. Prefer server-side exchange so the secret is not exposed. |
| Redirect URI | Must be registered in the application dashboard and must match during token exchange. Pandora's tutorial shows localhost as an example. | Local development needs an explicitly registered callback, exact URI matching, and a controlled local listener. Do not invent a production redirect before partner approval. |
| Scope | The authorization docs state that only `webapi` is supported and it is the default. | Request only `webapi`; do not implement undocumented scopes. |
| Access token | Returned by the authorization-code exchange; documented lifetime is 14,400 seconds in the tutorial response example. | Treat as ephemeral and never persist in the repository or logs. |
| Refresh | Refresh-token grant uses the same token endpoint, requires the refresh token and client Basic authentication, and returns a fresh access token. | TODO 655 may persist only a protected local refresh token after explicit approval and threat-model review; this spike stores none. |
| Revoke/sign-out | Certification requires OAuth sign-out/account disassociation and calls for the OAuth revoke endpoint. | Future adapter needs sign-out/revoke handling and token deletion. |
| Listener account | A Pandora listener account is required before API development. | This is separate from developer-partner access. |
| Subscription | Free, Plus, and Premium are supported, but playback rights differ. Free has ads, skip limits, and shorter timeout; Plus removes ad playback and skip limits; Premium adds on-demand track/album/playlist/podcast playback and playlist/album shuffle. Licensing and track rights can still limit playback or feedback. See [Pandora Subscriptions and the APIs](https://developer.pandora.com/docs/getting-started/pandora-subscriptions-and-apis/). | The adapter must inspect returned rights and account errors; it cannot promise Premium controls for every account or track. |

## 4. Requested capability matrix

| Requested capability | Official support | Boundary |
| --- | --- | --- |
| Station listing/presets | **Yes, partner API.** The API supports listener collections; the tutorial includes [showing all my Stations](https://developer.pandora.com/docs/tutorials/showing-all-my-stations/). It also documents Thumbprint, Shuffle, top artists, and recent favorites as playback sources. | Station factories can create a user station when first played. Station/source IDs and current state are account/device-specific. |
| Shuffle | **Yes, partner API.** The playback reference documents [set shuffle mode](https://developer.pandora.com/docs/reference/graphql-api/playback/set-shuffle-mode-source/), and the listener API documents a shuffle station. | Entitlement and source type still govern availability. Premium adds playlist/album shuffle. |
| Play/pause | **Yes, partner API.** Playback reference documents [pause](https://developer.pandora.com/docs/reference/graphql-api/playback/pause-track/) and [play/start](https://developer.pandora.com/docs/reference/graphql-api/playback/play-start-track/). | A client must send the corresponding playback events and maintain the current source/device context. |
| Skip | **Yes, conditional.** The API and certification checklist document skip; the returned `interactions` field tells the client whether `SKIP` is allowed. Free listeners have daily skip limits and thumbs-down can count toward the limit. | Never render skip unconditionally. Handle rights, limits, ads, idle timeout, and simultaneous-stream errors. |
| Thumbs-up | **Yes, conditional.** Feedback mutations support thumbs up/down and removal; `THUMB` in `interactions` indicates whether the current track allows it. | Track licensing/rights may disable feedback. A thumbs-up influences favorites and Thumbprint Radio. |
| Rewind/seek | **Not a guaranteed MVP control.** The interaction list may include `SEEK`, `FORWARD_15_SECONDS`, or `BACK_15_SECONDS`; radio audio cannot generally be rewound and rights vary. | Do not add this to TODO 655's MVP promise. |

Pandora's [allowed-interactions test scenarios](https://developer.pandora.com/docs/developer-resources/test-scenarios/allowed-interactions/) list `SKIP`, `THUMB`, and other interaction values. The [certification checklist](https://developer.pandora.com/docs/certification-checklist/) requires pause/play, skip-limit handling, station lists, thumbs-up behavior, OAuth sign-on, access-token refresh, and protection of partner credentials.

## 5. In-portal playback versus handoff

| Option | What it can deliver | Main risk/constraint | Assessment |
| --- | --- | --- | --- |
| Partner GraphQL + local audio element | Requested station presets, current track metadata, play/pause, conditional skip, conditional thumbs-up, shuffle, and account-aware rights handling. | Requires partner approval, app credentials, registered redirect, OAuth implementation, API certification, device UUID/state management, short-lived audio URL handling, and subscription/track-rights errors. | Strongest supported workflow, but gated. |
| Official Pandora destination handoff | Opens an official Pandora destination in the user's browser. No credentials or unofficial integration needed. | Playback and controls leave the portal; no documented control bridge or reliable station/preset handoff contract. | Safe fallback only; does not meet in-portal MVP. |
| Pandora page iframe or scraped web player | Potentially appears in a portal visually. | No official iframe/control contract found in current developer docs; scraping and unofficial APIs are explicitly out of scope. | Rejected. |

## 6. Consequences for TODO 655

TODO 655 is **not implementable yet** from this spike alone. Keep it blocked until all of the following are confirmed through Pandora's official partner process:

1. Partnership access is approved for the Music project/use case.
2. An application is created and its client ID/secret, redirect URI, publication status, and allowed environment are known to the human owner without placing secrets in the repository.
3. Pandora confirms the intended local-development redirect and any production redirect/domain requirements.
4. The target listener account's subscription tier and geographic/licensing availability are sufficient for the desired workflow.
5. Pandora's certification/contract requirements for a browser-based local client and audio delivery are accepted.

Once those gates are met, TODO 655 should specify a server-mediated authorization-code + PKCE flow, transient access tokens, protected local refresh-token storage, exact `webapi` scope, account sign-out/revoke, station collection loading, source/device state, just-in-time audio URL refresh, and controls driven by `interactions` rather than assumed. The adapter should expose a capability model so Free/Plus/Premium and per-track rights can disable controls cleanly.

If partnership access is denied or the contract does not permit this local browser workflow, close or revise TODO 655 to the official-handoff-only option and do not create a provider adapter or player bar. That outcome also means the parent TODO 651 cannot promise a Pandora radio surface.

## 7. Security and evidence controls

- No Pandora client ID, client secret, authorization code, access token, refresh token, password, or API response was stored in this repository or runtime data.
- Source examples were not executed and no API Explorer or OAuth login was used.
- No scraping, reverse engineering, unofficial endpoint, or browser automation was used.
- Future implementation must redact tokens and audio URLs from logs, avoid committing local credential files, and keep refresh-token storage outside tracked project files with OS protection.

## Sources

All sources below are official Pandora developer documentation or official Pandora destinations, accessed for this spike on 2026-09-13:

- [Pandora Developer Center](https://developer.pandora.com/)
- [Documentation overview](https://developer.pandora.com/docs/)
- [Support and API Features](https://developer.pandora.com/docs/overview/support-and-api-features/)
- [Partner Access](https://developer.pandora.com/docs/overview/partner-access/)
- [Applications](https://developer.pandora.com/docs/key-concepts/applications/)
- [Prerequisites](https://developer.pandora.com/docs/prerequisites/)
- [Becoming a Pandora Partner](https://developer.pandora.com/docs/getting-started/becoming-pandora-partner/)
- [Accessing the Developer Portal](https://developer.pandora.com/docs/getting-started/accessing-developer-portal/)
- [Pandora Subscriptions and the APIs](https://developer.pandora.com/docs/getting-started/pandora-subscriptions-and-apis/)
- [Authorization Code Grant](https://developer.pandora.com/docs/reference/graphql-api/authentication-using-oauth2/authorization-code-grant/)
- [Authentication and Authorization tutorial](https://developer.pandora.com/docs/tutorials/authenticate-app-user-pandora/authentication-authorization/)
- [Get access token tutorial](https://developer.pandora.com/docs/tutorials/authenticate-app-user-pandora/get-access-token/)
- [Refresh access token tutorial](https://developer.pandora.com/docs/tutorials/authenticate-app-user-pandora/optional-refresh-access-token-after-expiry/)
- [GraphQL playback reference](https://developer.pandora.com/docs/reference/graphql-api/playback/)
- [Playback with Pandora tutorial](https://developer.pandora.com/docs/tutorials/playback-pandora/)
- [Playback component tutorial](https://developer.pandora.com/docs/tutorials/station-playback/playback-component/)
- [Listener resources](https://developer.pandora.com/docs/reference/graphql-api/listener/)
- [Feedback reference](https://developer.pandora.com/docs/reference/graphql-api/feedback/)
- [Allowed interactions](https://developer.pandora.com/docs/developer-resources/test-scenarios/allowed-interactions/)
- [Certification checklist](https://developer.pandora.com/docs/certification-checklist/)
- [Things Every Developer Should Know](https://developer.pandora.com/docs/reference/graphql-api/overview/things-every-developer-should-know/)
- [Pandora AMP destination](https://amp.pandora.com/)

## Validation

- Markdown artifact is plain text/links only; no executable integration code was added.
- No credentials, tokens, secrets, or API responses were persisted.
- Worktree diff and secret scan must be run before the FR is advanced.
