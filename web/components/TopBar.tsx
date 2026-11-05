"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/", label: "시세 지도" },
  { href: "/check", label: "계약서 점검" },
];

export default function TopBar() {
  const path = usePathname();
  return (
    <header className="sticky top-0 z-[1000] flex h-14 shrink-0 items-center gap-6 border-b border-line bg-surface px-4 md:px-6">
      <Link href="/" className="flex items-baseline gap-2">
        <span className="text-[17px] font-extrabold tracking-[-0.02em] text-ink">계약 전에</span>
        <span className="hidden text-xs font-semibold text-sea sm:inline">삼척 자취방</span>
      </Link>
      <nav className="flex h-full items-stretch gap-1">
        {TABS.map((t) => {
          const active = t.href === "/" ? path === "/" : path.startsWith(t.href);
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
