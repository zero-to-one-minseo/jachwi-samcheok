import type { Metadata, Viewport } from "next";
import TopBar from "@/components/TopBar";
import "./globals.css";

export const metadata: Metadata = {
  title: "계약 전에 · 삼척 자취방",
  description: "삼척 학생들이 직접 모은 자취방 시세 지도와, 계약서를 올리면 확인할 조항을 짚어 주는 점검.",
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
