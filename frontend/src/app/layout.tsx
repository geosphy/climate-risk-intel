import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "ClimateRisk Intel — AI Climate Risk Assessment",
  description:
    "Open source AI-native climate risk intelligence platform. Enter any address to get flood, heat, and storm risk scores for your physical asset.",
  keywords: ["climate risk", "flood risk", "heat risk", "storm risk", "FEMA", "NOAA", "AI"],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={inter.className}>{children}</body>
    </html>
  );
}
