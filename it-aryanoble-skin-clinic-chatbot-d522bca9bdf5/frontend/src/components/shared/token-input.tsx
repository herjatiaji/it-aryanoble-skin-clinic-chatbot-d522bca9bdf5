"use client";

import { Input } from "@/components/ui/input";
import { formatCompactTokens, formatNumberWithCommas, parseRawNumber } from "@/lib/formatters";
import { cn } from "@/lib/utils";
import React, { useId, useState } from "react";

export interface TokenInputProps extends Omit<React.ComponentProps<"input">, "value" | "onChange"> {
	value: number | string;
	onChange: (value: number) => void;
	suffix?: string;
	showPreview?: boolean;
	previewSuffix?: string;
	min?: number;
	max?: number;
	className?: string;
	containerClassName?: string;
}

export function TokenInput({
	value,
	onChange,
	suffix = "tokens",
	showPreview = true,
	previewSuffix = "tokens / month",
	min = 0,
	max,
	disabled = false,
	placeholder = "0",
	className,
	containerClassName,
	id: propId,
	...props
}: TokenInputProps) {
	const defaultId = useId();
	const inputId = propId || defaultId;

	const [displayValue, setDisplayValue] = useState<string>(() =>
		value !== "" && value !== undefined && value !== null ? formatNumberWithCommas(value) : "",
	);

	// Track last external value to sync display value when props change externally
	const [prevValue, setPrevValue] = useState(value);
	if (value !== prevValue) {
		setPrevValue(value);
		const formatted =
			value !== "" && value !== undefined && value !== null ? formatNumberWithCommas(value) : "";
		setDisplayValue(formatted);
	}

	const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
		const rawInput = e.target.value;
		// Keep only digits
		const digitsOnly = rawInput.replace(/[^0-9]/g, "");

		if (!digitsOnly) {
			setDisplayValue("");
			onChange(0);
			return;
		}

		let num = parseInt(digitsOnly, 10);
		if (isNaN(num)) num = 0;
		if (min !== undefined && num < min) num = min;
		if (max !== undefined && num > max) num = max;

		const formatted = num.toLocaleString("en-US");
		setDisplayValue(formatted);
		onChange(num);
	};

	const numericValue = parseRawNumber(displayValue);
	const compactFormatted = formatCompactTokens(numericValue);

	return (
		<div className={cn("flex flex-col gap-1.5 w-full", containerClassName)}>
			<div className="relative flex items-center">
				<Input
					{...props}
					id={inputId}
					type="text"
					inputMode="numeric"
					disabled={disabled}
					placeholder={placeholder}
					value={displayValue}
					onChange={handleChange}
					onWheel={(e) => (e.target as HTMLInputElement).blur()}
					className={cn(
						"h-10 border-gray-200 bg-white text-foreground rounded-lg focus-visible:ring-blue-500 font-medium text-sm",
						suffix ? "pr-24" : "pr-3",
						className,
					)}
				/>
				{suffix && (
					<span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs font-medium text-muted-foreground pointer-events-none select-none">
						{suffix}
					</span>
				)}
			</div>

			{showPreview && numericValue > 0 && (
				<div className="flex items-center gap-1.5 text-xs text-muted-foreground px-0.5">
					<span>≈</span>
					<span className="font-semibold text-zinc-700">{compactFormatted}</span>
					<span>{previewSuffix}</span>
				</div>
			)}
		</div>
	);
}
