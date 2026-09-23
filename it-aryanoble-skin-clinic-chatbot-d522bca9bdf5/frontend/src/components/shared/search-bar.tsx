import { cn } from "@/lib/utils";
import { RiSearchLine } from "@remixicon/react";
import React from "react";

export interface SearchBarProps extends React.ComponentProps<"input"> {
	containerClassName?: string;
	iconClassName?: string;
}

export function SearchBar({
	className,
	containerClassName,
	iconClassName,
	type = "text",
	autoComplete = "off",
	spellCheck = false,
	...props
}: SearchBarProps) {
	return (
		<div className={cn("relative flex items-center w-full", containerClassName)}>
			<RiSearchLine
				className={cn(
					"absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground pointer-events-none z-10",
					iconClassName,
				)}
			/>
			<input
				type={type}
				autoComplete={autoComplete}
				spellCheck={spellCheck}
				className={cn(
					"h-10 w-full rounded-lg border border-gray-200 bg-white pl-9 pr-4 py-2 text-sm text-foreground placeholder:text-muted-foreground transition-all outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50",
					className,
				)}
				{...props}
			/>
		</div>
	);
}
