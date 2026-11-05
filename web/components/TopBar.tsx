"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSyncExternalStore } from "react";

const noSubscribe = () => () => {};

const TABS = [
  { href: "/", label: "평균 시세" },
  { href: "/chat", label: "매물 비교" },
  { href: "/check", label: "계약서 검사" },
];

export default function TopBar() {
  const path = usePathname();
  // 상단 줄은 모든 페이지가 같이 쓰는 미리 그린 틀이라 서버는 지금 주소를 모른다. 붙은 뒤에만 현재 탭을 표시한다.
  const hydrated = useSyncExternalStore(noSubscribe, () => true, () => false);
  return (
    <header className="sticky top-0 z-[1000] flex h-14 shrink-0 items-center gap-6 border-b border-line bg-surface px-4 md:px-6">
      <Link href="/" className="flex items-baseline gap-2">
        <span className="text-[17px] font-extrabold tracking-[-0.02em] text-ink">자취학과</span>
        <span className="hidden text-xs font-semibold text-sea sm:inline">삼척 자취방</span>
      </Link>
      <nav className="flex h-full items-stretch gap-1">
        {TABS.map((t) => {
          const active = hydrated && (t.href === "/" ? path === "/" : path.startsWith(t.href));
          return (
            <Link
              key={t.href}
              href={t.href}
              aria-current={active ? "page" : undefined}
              className={`flex items-center border-b-2 px-3 text-[15px] font-semibold transition-colors ${
                active ? "border-sea text-ink" : "border-transparent text-muted hover:text-ink"
              }`}
            >
              {t.label}
            </Link>
          );
        })}
      </nav>
    </header>
  );
}
