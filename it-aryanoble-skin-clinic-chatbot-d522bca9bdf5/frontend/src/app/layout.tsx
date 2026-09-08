import type { Metadata } from "next";
import { Inter, Geist_Mono } from "next/font/google";
import "./globals.css";
import { cn } from "@/lib/utils";

import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryProvider } from "@/components/providers/query-provider";
import { Toaster } from "@/components/ui/sonner";

import { AuthProvider } from "@/hooks/use-session";

const inter = Inter({ subsets: ['latin'], variable: '--font-sans' });

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Arya Noble Chatbot",
  description: "AI-powered chatbot interface for doctors and admin",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={cn("h-full", "antialiased", geistMono.variable, inter.variable, "font-sans")}
    >
      <body className="min-h-full flex flex-col">
        <QueryProvider>
          <AuthProvider>
            <TooltipProvider>{children}</TooltipProvider>
          </AuthProvider>
          <Toaster />
        </QueryProvider>
      </body>
    </html>
  );
}
