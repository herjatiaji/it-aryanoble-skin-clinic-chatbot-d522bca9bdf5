import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { RiSearchLine } from "@remixicon/react";
import React from "react";

export interface SearchBarProps extends React.ComponentProps<"input"> {
	containerClassName?: string;
	iconClassName?: string;
}

export function SearchBar({ className, containerClassName, iconClassName, ...props }: SearchBarProps) {
	return (
		<div className={cn("relative flex items-center w-full", containerClassName)}>
			<RiSearchLine className={cn("absolute left-2.5 w-4 h-4 text-gray-400", iconClassName)} />
			<Input type="search" {...props} className={cn("pl-8 bg-white", className)} />
		</div>
	);
}
