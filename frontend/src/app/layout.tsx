import type { Metadata } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import "./globals.css";
import { Providers } from "@/components/providers";
import { Sidebar } from "@/components/sidebar";

export const metadata: Metadata = {
  title: "Chess Analyzer",
  description: "Analyze your chess games. Find your weaknesses. Get better.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${GeistSans.variable} ${GeistMono.variable}`}>
      <body className="bg-surface-0 text-white antialiased">
        <Providers>
          <div className="flex h-screen overflow-hidden">
            <Sidebar />
            <main className="flex-1 overflow-y-auto pb-20 md:pb-0">{children}</main>
          </div>
        </Providers>
      </body>
    </html>
  );
}
