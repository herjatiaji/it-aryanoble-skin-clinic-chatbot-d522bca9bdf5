"use client";


import { GlobalTokenConfig } from "./components/global-token-config";
import { GlobalModelConfig } from "./components/global-model-config";
import { GlobalTimeLimitConfig } from "./components/global-time-limit-config";
import { GlobalFileAttachmentConfig } from "./components/global-file-attachment-config";

export default function ConfigPage() {
	return (
		<div className="flex flex-col flex-1 min-h-full bg-white p-6">
			<div className="flex flex-col gap-6 w-full">
				{/* Header */}
				<div className="flex flex-col gap-1">
					<h1 className="text-xl font-semibold text-black-500">Configuration</h1>
					<p className="text-sm text-black-300">Here is the overview data of the configuration</p>
				</div>

				{/* Content */}
				<div className="flex flex-col gap-4">
					<GlobalModelConfig />
					<GlobalTokenConfig />
					<GlobalTimeLimitConfig />
					<GlobalFileAttachmentConfig />
				</div>
			</div>
		</div>
	);
}
