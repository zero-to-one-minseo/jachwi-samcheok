import RoomsApp from "@/components/rooms/RoomsApp";
import data from "@/public/data/rooms.json";
import type { RoomsData } from "@/lib/rooms";

export default function Home() {
  return <RoomsApp data={data as unknown as RoomsData} />;
}
