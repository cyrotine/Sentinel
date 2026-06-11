import type { Metadata } from "next";
import { AppShell } from "@/components/app-shell";
import "./globals.css";

export const metadata: Metadata = {
  title: "Forge",
  description: "Autonomous Multi-Agent Open Source Engineer",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark antialiased">
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
