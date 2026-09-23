import { RiGitMergeLine, RiGitRepositoryLine } from "@remixicon/react";

interface IngestShortcutCardsProps {
	isGeneralMode: boolean;
	onSelectPrompt: (prompt: string) => void;
}

export function IngestShortcutCards({ isGeneralMode, onSelectPrompt }: IngestShortcutCardsProps) {
	if (isGeneralMode) return null;

	return (
		<div className="grid grid-cols-2 gap-3 w-full mb-4 shrink-0">
			<button
				type="button"
				onClick={() =>
					onSelectPrompt(
						"Analyze all uploaded documents and treat them as a unified knowledge base. Identify key information and cross-document relationships while ensuring that all findings remain strictly grounded in the provided sources. If the source knowledge is primarily in Indonesian, generate the response in Indonesian.",
					)
				}
				className="flex flex-col items-start p-3 text-left rounded-lg border border-zinc-200/70 bg-white hover:border-zinc-300 hover:bg-zinc-50/60 transition-all cursor-pointer shadow-none"
			>
				<RiGitRepositoryLine className="size-4 text-zinc-950 mb-1.5" />
				<h3 className="font-semibold text-xs text-zinc-950 mb-0.5">Unified Knowledge Analysis</h3>
				<p className="text-[11px] leading-tight text-zinc-600 line-clamp-2">
					Analyze all uploaded documents and treat them as a unified knowledge base...
				</p>
			</button>
			<button
				type="button"
				onClick={() =>
					onSelectPrompt(
						"Review all uploaded files and map key entities, topics, and relationships across documents. Clearly distinguish between available information and information that is not provided in the knowledge base. If the source knowledge is primarily in Indonesian, generate the response in Indonesian.",
					)
				}
				className="flex flex-col items-start p-3 text-left rounded-lg border border-zinc-200/70 bg-white hover:border-zinc-300 hover:bg-zinc-50/60 transition-all cursor-pointer shadow-none"
			>
				<RiGitMergeLine className="size-4 text-zinc-950 mb-1.5" />
				<h3 className="font-semibold text-xs text-zinc-950 mb-0.5">Entity & Topic Mapping</h3>
				<p className="text-[11px] leading-tight text-zinc-600 line-clamp-2">
					Review all uploaded files and map key entities, topics, and relationships across
					documents...
				</p>
			</button>
		</div>
	);
}
