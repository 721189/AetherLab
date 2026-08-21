/**
 * Sentry browser-side initialization.
 *
 * @sentry/nextjs auto-loads this file on the client. When NEXT_PUBLIC_SENTRY_DSN
 * is unset the SDK is a no-op, so development/local builds are unaffected.
 *
 * @see https://docs.sentry.io/platforms/javascript/guides/nextjs/
 */
import * as Sentry from "@sentry/nextjs";

const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;

if (dsn) {
  Sentry.init({
    dsn,
    tracesSampleRate: Number(
      process.env.NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE ?? 0.1
    ),
    sendDefaultPii: false,
    environment: process.env.NODE_ENV,
  });

  // Tag every event so it can be filtered to the frontend component.
  Sentry.setTag("component", "aetherlab-frontend");
}
