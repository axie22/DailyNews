import type { Metadata } from "next";
import Link from "next/link";
import ThemeToggle from "@/components/ThemeToggle";
import "./globals.css";

export const metadata: Metadata = {
  title: "ML News",
  description: "Daily ML research digest",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen bg-[#fafafa] dark:bg-gray-950">
        <header className="border-b border-gray-200 dark:border-gray-800 bg-white/80 dark:bg-gray-900/80 backdrop-blur-sm sticky top-0 z-10">
          <div className="max-w-3xl mx-auto px-4 h-12 flex items-center justify-between">
            <Link href="/" className="flex items-center gap-2.5 hover:opacity-80 transition-opacity">
              <div className="w-7 h-7 bg-gray-900 dark:bg-gray-100 rounded-lg flex items-center justify-center">
                <span className="text-white dark:text-gray-900 text-[11px] font-bold tracking-tight">ML</span>
              </div>
              <div className="flex items-baseline gap-1.5">
                <span className="font-bold text-[15px] tracking-tight dark:text-gray-100">ML News</span>
                <span className="text-[10px] text-gray-400 dark:text-gray-500 hidden sm:inline">daily digest</span>
              </div>
            </Link>
            <div className="flex items-center gap-1">
              <Link
                href="/digest"
                className="px-2.5 py-1 rounded-lg text-xs font-medium text-gray-500 hover:text-gray-700 hover:bg-gray-100 dark:text-gray-400 dark:hover:text-gray-200 dark:hover:bg-gray-800 transition-colors"
              >
                Digest
              </Link>
              <ThemeToggle />
            </div>
          </div>
        </header>
        <main className="max-w-3xl mx-auto px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
