import * as React from "react"
import { cn } from "@/lib/utils"
import { RiLoaderLine } from "@remixicon/react"

function Spinner({ className, ...props }: React.ComponentProps<"svg">) {
  return (
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    <RiLoaderLine data-slot="spinner" role="status" aria-label="Loading" className={cn("size-4 animate-spin", className)} {...(props as any)} />
  )
}

export { Spinner }
