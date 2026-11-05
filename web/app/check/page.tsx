import type { Metadata } from "next";
import { Suspense } from "react";
import CheckApp from "@/components/check/CheckApp";
import data from "@/public/data/rooms.json";
import type { RoomsData } from "@/lib/rooms";

export const metadata: Metadata = { title: "계약서 점검 · 계약 전에" };

export default function CheckPage() {
  return (
    <Suspense>
      <CheckApp rooms={(data as unknown as RoomsData).rooms} />
    </Suspense>
  );
}
