import { RiAlertLine } from "@remixicon/react";

interface QuotaData {
	exceeded?: boolean;
	warning?: boolean;
	percentage: number;
	tokens_used: number;
	token_limit: number;
}

interface IngestQuotaAlertProps {
	isGeneralMode: boolean;
	quota?: QuotaData | null;
}

export function IngestQuotaAlert({ isGeneralMode, quota }: IngestQuotaAlertProps) {
	if (isGeneralMode || !quota || (!quota.exceeded && !quota.warning)) {
		return null;
	}

	return (
		<div className="mb-5 w-full">
			{quota.exceeded ? (
				<div className="flex items-start gap-3 p-3.5 rounded-lg border border-amber-300 bg-white text-xs">
					<RiAlertLine className="size-4 text-amber-600 shrink-0 mt-0.5" />
					<div className="flex flex-col gap-0.5">
						<span className="font-semibold text-zinc-900">
							Monthly Ingestion Limit Reached ({quota.percentage}%)
						</span>
						<span className="text-zinc-600">
							Used {quota.tokens_used.toLocaleString()} of {quota.token_limit.toLocaleString()}{" "}
							tokens. Ingestion will proceed, but threshold can be adjusted in Configuration.
						</span>
					</div>
				</div>
			) : (
				<div className="flex items-start gap-3 p-3.5 rounded-lg border border-amber-300 bg-white text-xs">
					<RiAlertLine className="size-4 text-amber-600 shrink-0 mt-0.5" />
					<div className="flex flex-col gap-0.5">
						<span className="font-semibold text-zinc-900">Monthly Ingestion Near Limit</span>
						<span className="text-zinc-600">
							{quota.tokens_used.toLocaleString()} of {quota.token_limit.toLocaleString()} tokens
							used ({quota.percentage}%).
						</span>
					</div>
				</div>
			)}
		</div>
	);
}
