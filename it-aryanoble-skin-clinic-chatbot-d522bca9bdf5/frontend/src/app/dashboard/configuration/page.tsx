"use client";

import { GlobalFileAttachmentConfig } from "./components/global-file-attachment-config";
import { GlobalModelConfig } from "./components/global-model-config";
import { GlobalMonthlyUsage } from "./components/global-monthly-usage";
import { GlobalTimeLimitConfig } from "./components/global-time-limit-config";
import { GlobalTokenConfig } from "./components/global-token-config";

export default function ConfigPage() {
	return (
		<div className="flex flex-col flex-1 min-h-full bg-white p-6">
			<div className="flex flex-col gap-6 w-full">
				{/* 1. Global Monthly Token Usage */}
				<GlobalMonthlyUsage />

				{/* 2. Configuration title and subtitle */}
				<div className="flex flex-col gap-1">
					<h1 className="text-xl font-semibold text-foreground">Configuration</h1>
					<p className="text-sm text-muted-foreground">
						Here is the overview data of the configuration
					</p>
				</div>

				{/* Content Sections */}
				<div className="flex flex-col gap-4">
					{/* 3. Global Token Configuration */}
					<GlobalTokenConfig />

					{/* 4. AI Prompt File Attachments */}
					<GlobalFileAttachmentConfig />

					{/* 5. Time Limit Per Session */}
					<GlobalTimeLimitConfig />

					{/* 6. Global AI Model Configuration */}
					<GlobalModelConfig />
				</div>
			</div>
		</div>
	);
}
