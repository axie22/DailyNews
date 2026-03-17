import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "ML News",
  description: "Daily ML research digest",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-[#fafafa]">
        <header className="border-b border-gray-200 bg-white/80 backdrop-blur-sm sticky top-0 z-10">
          <div className="max-w-3xl mx-auto px-4 h-12 flex items-center justify-between">
            <Link href="/" className="flex items-center gap-2.5 hover:opacity-80 transition-opacity">
              <div className="w-7 h-7 bg-gray-900 rounded-lg flex items-center justify-center">
                <span className="text-white text-[11px] font-bold tracking-tight">ML</span>
              </div>
              <div className="flex items-baseline gap-1.5">
                <span className="font-bold text-[15px] tracking-tight">ML News</span>
                <span className="text-[10px] text-gray-400 hidden sm:inline">daily digest</span>
              </div>
            </Link>
          </div>
        </header>
        <main className="max-w-3xl mx-auto px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
