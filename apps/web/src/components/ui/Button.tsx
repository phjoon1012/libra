"use client";

import clsx from "clsx";
import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "ghost";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
}

const VARIANT_CLASS: Record<Variant, string> = {
  primary: "bg-white text-black hover:bg-white/85 active:bg-white/75",
  secondary:
    "bg-transparent text-white border border-white/15 hover:border-white/40 hover:text-white",
  ghost:
    "bg-transparent text-white/40 border border-transparent hover:text-white",
};

export function Button({ variant = "secondary", className, children, ...rest }: Props) {
  return (
    <button
      {...rest}
      className={clsx(
        "inline-flex h-9 items-center justify-center gap-2 rounded-full px-4 text-[11px] font-medium uppercase tracking-[0.22em] transition disabled:cursor-not-allowed disabled:opacity-30",
        VARIANT_CLASS[variant],
        className,
      )}
    >
      {children}
    </button>
  );
}
