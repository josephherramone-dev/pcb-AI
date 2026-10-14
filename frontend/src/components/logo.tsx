import { Cpu } from "lucide-react";
import Link from "next/link";

export function Logo() {
  return (
    <Link href="/" className="flex items-center gap-2 font-semibold">
      <span className="flex h-6 w-6 items-center justify-center rounded bg-accent text-accent-fg">
        <Cpu className="h-3.5 w-3.5" />
      </span>
      <span className="text-[13px]">PCB AI</span>
    </Link>
  );
}
