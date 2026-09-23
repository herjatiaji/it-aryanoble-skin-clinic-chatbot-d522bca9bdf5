"use client";

import { useConfigs, useGlobalMonthlyUsage } from "../hooks/use-config";
import { MonthlyUsageSkeleton } from "./skeletons/monthly-usage-skeleton";

export function GlobalMonthlyUsage() {
	const { data: usage, isLoading: isUsageLoading } = useGlobalMonthlyUsage();
	const { data: configs, isLoading: isConfigsLoading } = useConfigs();

	const isLoading = isUsageLoading || isConfigsLoading;

	// Check if global limit config and threshold are active from configs (authoritative) or usage endpoint
	const isMasterActive =
		configs?.find((c) => c.key === "GLOBAL_TOKEN_LIMIT_ACTIVE")?.value === "true";
	const isThresholdActive =
		configs?.find((c) => c.key === "GLOBAL_THRESHOLD_ACTIVE")?.value === "true";
	const isGlobalLimitActive =
		isMasterActive && isThresholdActive
			? true
			: isMasterActive === false
				? false
				: usage?.is_global_active === true;

	const tokensUsed = usage?.tokens_used ?? 0;
	const tokenLimit = usage?.token_limit ?? 1000000;
	const rawPercentage = usage?.percentage ?? (tokenLimit > 0 ? (tokensUsed / tokenLimit) * 100 : 0);
	const percentage = Math.min(100, Math.max(0, Math.round(rawPercentage)));

	// Format numbers using dot notation (id-ID locale) consistent with Figma design
	const formatNumber = (num: number) => {
		return new Intl.NumberFormat("id-ID").format(num);
	};

	if (isLoading) {
		return <MonthlyUsageSkeleton />;
	}

	// SVG Donut Chart calculation
	const size = 68;
	const strokeWidth = 10;
	const radius = (size - strokeWidth) / 2;
	const circumference = 2 * Math.PI * radius;
	const strokeDashoffset = circumference - (percentage / 100) * circumference;

	return (
		<div className="flex flex-col w-full">
			<div className="flex flex-col gap-6 border border-white-600 rounded-lg p-4 bg-white">
				{/* Title and Subtitle */}
				<div className="flex flex-col gap-1">
					<h3 className="text-base font-medium text-black-500">Global Monthly Token Usage</h3>
					<p className="text-sm text-black-300">
						Monitor total AI token consumption and monthly usage limits across the system.
					</p>
				</div>

				{/* Usage Section */}
				<div className="flex flex-col sm:flex-row sm:items-center gap-6">
					{isGlobalLimitActive ? (
						<>
							{/* Donut Progress Chart with Percentage */}
							<div className="relative flex items-center justify-center shrink-0 size-17">
								<svg
									width={size}
									height={size}
									viewBox={`0 0 ${size} ${size}`}
									className="-rotate-90"
								>
									{/* Background Track */}
									<circle
										cx={size / 2}
										cy={size / 2}
										r={radius}
										fill="transparent"
										stroke="#dedede"
										strokeWidth={strokeWidth}
									/>
									{/* Progress Circle */}
									<circle
										cx={size / 2}
										cy={size / 2}
										r={radius}
										fill="transparent"
										stroke="#0081f5"
										strokeWidth={strokeWidth}
										strokeDasharray={circumference}
										strokeDashoffset={strokeDashoffset}
										strokeLinecap="round"
										className="transition-all duration-500 ease-in-out"
									/>
								</svg>
								<span className="absolute text-sm font-medium text-black-500">{percentage}%</span>
							</div>

							{/* Usage Remaining Box */}
							<div className="flex flex-col gap-1.5 flex-1 max-w-md">
								<span className="text-sm text-black-300">Monthly Usage (Used / Limit)</span>
								<div className="h-10 px-3.5 bg-[#f0f0f0] border border-white-600 rounded-lg flex items-center text-sm text-black-400">
									<span>
										{formatNumber(tokensUsed)} / {formatNumber(tokenLimit)}
									</span>
								</div>
							</div>
						</>
					) : (
						/* When Global Token Config is Inactive: Display total usage */
						<div className="flex flex-col gap-1.5 flex-1 max-w-md">
							<span className="text-sm text-black-300">Total Monthly Token Usage</span>
							<div className="h-10 px-3.5 bg-[#f0f0f0] border border-white-600 rounded-lg flex items-center text-sm text-black-400">
								<span>{formatNumber(tokensUsed)} tokens</span>
							</div>
						</div>
					)}
				</div>
			</div>
		</div>
	);
}
