import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "@/lib/query/providers";

export const metadata: Metadata = {
  title: "AetherLab — Environmental Intelligence",
  description:
    "Monitor air quality, weather and environmental conditions with an AI assistant.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen bg-background font-sans antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
