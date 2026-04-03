import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Geosphy™ — Data Center Climate Risk Intelligence",
  description:
    "AI-native climate risk intelligence for data centers. Physical risk assessment with EU regulatory compliance: CSRD/ESRS E1, EU Taxonomy, DORA.",
  keywords: ["climate risk", "data center", "CSRD", "ESRS E1", "EU Taxonomy", "DORA", "flood risk", "heat risk"],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className={inter.className}>{children}</body>
    </html>
  );
}
