import type { Metadata } from "next";
import ChatApp from "@/components/chat/ChatApp";

export const metadata: Metadata = { title: "매물 비교 · 자취학과" };

export default function ChatPage() {
  return <ChatApp />;
}
