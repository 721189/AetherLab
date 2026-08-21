/**
 * Sentry server-side initialization.
 *
 * @sentry/nextjs auto-loads this file for server components, API routes, and
 * middleware. Guarded on SENTRY_DSN so it is a no-op without configuration.
 *
 * @see https://docs.sentry.io/platforms/javascript/guides/nextjs/
 */
import * as Sentry from "@sentry/nextjs";

const dsn = process.env.SENTRY_DSN;

if (dsn) {
  Sentry.init({
    dsn,
    tracesSampleRate: Number(process.env.SENTRY_TRACES_SAMPLE_RATE ?? 0.1),
    sendDefaultPii: false,
    environment: process.env.NODE_ENV,
  });

  // Tag every event so it can be filtered to the frontend component.
  Sentry.setTag("component", "aetherlab-frontend");
}
