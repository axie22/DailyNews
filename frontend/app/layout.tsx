import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ML News",
  description: "Daily ML research digest",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gray-50">
        <header className="border-b bg-white sticky top-0 z-10">
          <div className="max-w-5xl mx-auto px-4 py-3 flex items-center gap-3">
            <span className="font-bold text-lg tracking-tight">ML News</span>
            <span className="text-xs text-gray-400">daily digest</span>
          </div>
        </header>
        <main className="max-w-5xl mx-auto px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
