import type { Metadata, Viewport } from "next";
import TopBar from "@/components/TopBar";
import "./globals.css";

export const metadata: Metadata = {
  title: "자취학과 · 삼척 자취방",
  description: "삼척 자취방 평균 시세, 매물 비교, 계약서 검사.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#ffffff",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ko" className="h-full">
      <body className="flex min-h-full flex-col">
        <TopBar />
        <div className="flex flex-1 flex-col">{children}</div>
      </body>
    </html>
  );
}
