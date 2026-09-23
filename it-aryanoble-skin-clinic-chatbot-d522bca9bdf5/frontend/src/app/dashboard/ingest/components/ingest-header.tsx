import { RiRobot2Line } from "@remixicon/react";

interface IngestHeaderProps {
	isGeneralMode: boolean;
}

export function IngestHeader({ isGeneralMode }: IngestHeaderProps) {
	return (
		<div className="flex flex-col items-center text-center space-y-2 mb-8">
			<div className="flex aspect-square size-12 items-center justify-center rounded-md bg-blue-50 text-blue-500">
				<RiRobot2Line className="size-6" />
			</div>
			<div className="space-y-1">
				<h1 className="text-xl font-semibold text-foreground">
					{isGeneralMode ? "Knowledge Base Assistant" : "Expand Knowledge Base"}
				</h1>
				<p className="text-sm text-muted-foreground max-w-95 leading-relaxed">
					{isGeneralMode
						? "Search and explore existing knowledge entries by asking questions via prompt."
						: "Upload product, treatment, or brochure documents to train the AI assistant."}
				</p>
			</div>
		</div>
	);
}
