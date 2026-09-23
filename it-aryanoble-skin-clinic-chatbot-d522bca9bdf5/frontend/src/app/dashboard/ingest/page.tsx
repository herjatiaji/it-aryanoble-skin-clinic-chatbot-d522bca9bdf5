"use client";

import { RiAlertLine } from "@remixicon/react";
import { Suspense } from "react";
import { IngestHeader } from "./components/ingest-header";
import { IngestModeControls } from "./components/ingest-mode-controls";
import { IngestQuotaAlert } from "./components/ingest-quota-alert";
import { IngestShortcutCards } from "./components/ingest-shortcut-cards";
import { PromptInput } from "./components/prompt-input";
import { IngestSkeleton } from "./components/skeletons/ingest-skeleton";
import { useIngestState } from "./hooks/use-ingest-state";

function IngestContent() {
	const {
		projectId,
		projects,
		quota,
		uploadProgress,
		isProcessing,
		mode,
		setMode,
		isGeneralMode,
		selectedProjectId,
		setSelectedProjectId,
		selectedProjectName,
		errorMsg,
		setErrorMsg,
		promptValue,
		setPromptValue,
		handleSend,
	} = useIngestState();

	return (
		<div className="flex flex-col max-w-2xl mx-auto min-h-full w-full pt-10 pb-10 px-4">
			<IngestHeader isGeneralMode={isGeneralMode} />

			<IngestQuotaAlert isGeneralMode={isGeneralMode} quota={quota} />

			<IngestShortcutCards
				isGeneralMode={isGeneralMode}
				onSelectPrompt={(prompt) => setPromptValue(prompt)}
			/>

			<div className="shrink-0 mt-4 flex flex-col items-center relative">
				<div className="w-full">
					<PromptInput
						key={mode}
						autoFocus
						value={promptValue}
						onValueChange={setPromptValue}
						minRows={5}
						onSend={handleSend}
						showAttachButton={!isGeneralMode}
						showAttachText={!isGeneralMode}
						attachText="Add files"
						placeholder={isGeneralMode ? "Ask about the knowledge..." : undefined}
						disabled={isProcessing}
						isLoading={isProcessing}
						uploadProgress={uploadProgress}
					/>
				</div>

				{errorMsg && (
					<div className="w-full mt-2 flex items-center text-[13px] font-medium text-amber-600 bg-amber-50 border border-amber-200/80 rounded-lg p-2.5">
						<RiAlertLine className="size-4 mr-1.5 shrink-0" />
						{errorMsg}
					</div>
				)}

				<IngestModeControls
					isGeneralMode={isGeneralMode}
					isProcessing={isProcessing}
					projectId={projectId}
					projects={projects}
					selectedProjectId={selectedProjectId}
					selectedProjectName={selectedProjectName}
					onModeChange={(newMode) => {
						setMode(newMode);
						setErrorMsg(null);
					}}
					onSelectProject={(val) => setSelectedProjectId(val)}
				/>
			</div>
		</div>
	);
}

export default function IngestPage() {
	return (
		<Suspense fallback={<IngestSkeleton />}>
			<IngestContent />
		</Suspense>
	);
}
