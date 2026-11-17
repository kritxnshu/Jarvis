# Product Spec

The authoritative, detailed spec — every capability's build list and acceptance tests — is
[docs/BRIEF.md](docs/BRIEF.md) §4 and §9. This page is the short product view.

## What JARVIS is

A macOS desktop app where the user states an intention and JARVIS understands, plans, acts
through tools, verifies the outcome, and reports back with a receipt. It knows the user's
confirmed memories, projects and preferences, and only the parts of the computer they have granted.

## Trust promises to the user

1. JARVIS never says "done" without evidence; unverified outcomes are labelled as such.
2. Consequential actions wait for your approval, bound to the exact action; the riskiest ones
   need a native macOS confirmation.
3. JARVIS never stores a memory silently; only your confirm action makes a memory confirmed,
   and content from web pages or files can't steer later conversations until you confirm it.
4. Every action is in an audit log you can search and export.
5. If JARVIS doesn't know whether something happened (crash, timeout), it says so and asks.
6. Deleting files moves them to a JARVIS trash you can restore from.

## Capabilities by release

| Release | Capabilities |
|---|---|
| v0.1 | 4.1 text chat · 4.2 memory · 4.3 provider switching · 4.6 files · 4.10 receipts (single actions, recovery) · 4.11 approvals · 4.12 audit |
| v0.2 | 4.7 terminal · 4.8 multi-step planning · 4.9 background tasks · 4.10 multi-step receipts |
| v0.3 | 4.4 browser · 4.5 desktop observation · 4.1 voice · 4.10 browser receipts |

Capabilities not yet released appear in the app with an explicit "Not available yet" state.

## Screens (all present from v0.1)

Command Center · Activity Center · Memory Center · Skills Center · Provider Settings ·
Security Center · Task History. Details: BRIEF §9.

## Design direction

Deep navy / near-black base, restrained electric-blue and cyan accents, excellent typography,
subtle motion, functional visualizations. No heavy glows, gratuitous gradients or "AI dashboard"
templates. WCAG AA, full keyboard navigation, reduced-motion support. All tokens in one file.
