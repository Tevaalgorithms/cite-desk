import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CiteDesk",
  description: "Handbook answers with a source for every sentence",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
