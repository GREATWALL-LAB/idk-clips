# Supabase Auth setup for IDK Clips

IDK Clips uses Supabase Auth only to email one-time codes and check them (account
verification and password reset). Accounts, passwords and data stay in IDK Clips' own
database. The hosted site uses the Supabase project `idk-clips` (Free plan).

| Supabase setting | Value |
|---|---|
| Authentication > Sign In / Providers > Email | Email enabled, **Email OTP Expiration 600 s**, **OTP length 6** |
| Authentication > Emails > Templates > Magic Link | Subject `{{ .Token }} is your IDK Clips code`, body `templates/verify-code.html` |
| Authentication > Emails > Templates > Confirm signup | Same subject and body as Magic Link |
| Authentication > Emails > Templates > Reset Password | Subject `{{ .Token }} is your IDK Clips password reset code`, body `templates/reset-code.html` |
| Authentication > URL Configuration | Site URL `https://idk-clips.vercel.app` |
| Authentication > Emails > SMTP Settings | Custom SMTP with sender name **IDK Clips** (see below) |

The templates show only the code (`{{ .Token }}`), never a sign-in link, because IDK Clips
verifies codes on its own server.

## Email delivery

Supabase's built-in sender only delivers to members of the Supabase organization and only
a few emails per hour, so it is enough to test the flow but not to serve the public. For
real users, connect an SMTP provider in SMTP Settings (sender name "IDK Clips", the
provider's host, port 465, user and API key as password). The API key is entered there,
in Supabase, and never stored in this repository or in the website's configuration.

Sending from your own domain needs these DNS records at the domain's DNS host (the
provider shows the exact values when you add the domain):

- **SPF**: a TXT record such as `v=spf1 include:<provider's SPF domain> ~all`;
- **DKIM**: the TXT or CNAME record(s) with the provider's public key;
- **DMARC**: a TXT record at `_dmarc.<your domain>`, for example
  `v=DMARC1; p=quarantine; rua=mailto:<your address>`.

A `*.vercel.app` address cannot carry these records, so delivery to everyone needs a
domain you control.

## IDK Clips settings

`OPENCLIP_SUPABASE_URL` (the project URL) and `OPENCLIP_SUPABASE_ANON_KEY` (the public
anon / publishable key, never the service-role key) are set in Vercel. Code lifetime,
resend cooldown and attempt limits are enforced by IDK Clips as well
(`OPENCLIP_EMAIL_OTP_TTL_MINUTES=10`, `..._RESEND_SECONDS=60`, `..._MAX_ATTEMPTS=5`).
