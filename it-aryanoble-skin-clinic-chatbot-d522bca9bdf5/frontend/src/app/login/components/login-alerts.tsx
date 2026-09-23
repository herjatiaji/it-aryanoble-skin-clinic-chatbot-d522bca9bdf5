import { RiErrorWarningLine } from "@remixicon/react";

interface LoginAlertsProps {
	reasonMessage: string | null;
	loginError: string | null;
}

export function LoginAlerts({ reasonMessage, loginError }: LoginAlertsProps) {
	return (
		<>
			{reasonMessage && !loginError && (
				<div className="flex items-center gap-3 text-sm font-medium text-amber-700 bg-amber-50 dark:bg-amber-950/40 dark:text-amber-300 p-3 rounded-lg mb-2 border border-amber-200 dark:border-amber-800">
					<RiErrorWarningLine className="h-5 w-5 shrink-0 text-amber-600 dark:text-amber-400" />
					<span className="leading-tight">{reasonMessage}</span>
				</div>
			)}

			{loginError && (
				<div className="flex items-center gap-3 text-sm font-medium text-destructive bg-destructive/10 p-3 rounded-lg mb-2">
					<RiErrorWarningLine className="h-5 w-5 shrink-0" />
					<span className="leading-tight">{loginError}</span>
				</div>
			)}
		</>
	);
}
