import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import { RiFileTextLine } from "@remixicon/react";

interface ProjectItem {
	id: string;
	name: string;
}

interface IngestModeControlsProps {
	isGeneralMode: boolean;
	isProcessing: boolean;
	projectId: string | null;
	projects: ProjectItem[];
	selectedProjectId: string;
	selectedProjectName: string;
	onModeChange: (mode: "ingest" | "general") => void;
	onSelectProject: (projectId: string) => void;
}

export function IngestModeControls({
	isGeneralMode,
	isProcessing,
	projectId,
	projects,
	selectedProjectId,
	selectedProjectName,
	onModeChange,
	onSelectProject,
}: IngestModeControlsProps) {
	return (
		<>
			{/* Mode Switch & Controls below prompt input */}
			<div className="w-full flex flex-wrap items-center justify-between gap-3 mt-3 px-0.5">
				{/* Toggle Switch: Ingest [Switch] Prompting */}
				<div className="flex items-center gap-2.5">
					<button
						type="button"
						onClick={() => {
							if (!isProcessing) {
								onModeChange("ingest");
							}
						}}
						className={cn(
							"text-sm cursor-pointer select-none transition-colors",
							!isGeneralMode ? "font-medium text-zinc-900" : "text-zinc-500 hover:text-zinc-800",
						)}
					>
						Ingest
					</button>
					<Switch
						id="ingest-mode-toggle"
						checked={isGeneralMode}
						onCheckedChange={(checked) => {
							onModeChange(checked ? "general" : "ingest");
						}}
						disabled={isProcessing}
						className="data-checked:bg-blue-500 data-[state=checked]:bg-blue-500 cursor-pointer"
					/>
					<button
						type="button"
						onClick={() => {
							if (!isProcessing) {
								onModeChange("general");
							}
						}}
						className={cn(
							"text-sm cursor-pointer select-none transition-colors",
							isGeneralMode ? "font-medium text-zinc-900" : "text-zinc-500 hover:text-zinc-800",
						)}
					>
						Prompting
					</button>
				</div>

				{/* Right Side: Project selector only when navigated from Project detail page, or helper for General */}
				{!isGeneralMode && Boolean(projectId && projectId !== "none") ? (
					<div className="flex items-center gap-2 max-w-full">
						<span className="text-xs text-zinc-500 font-medium shrink-0">Project:</span>
						<Select
							value={selectedProjectId}
							onValueChange={(val) => onSelectProject(val ?? "none")}
							disabled={isProcessing}
						>
							<SelectTrigger className="h-7.5 text-xs border border-zinc-200 bg-white text-zinc-700 rounded-md px-2.5 min-w-36 max-w-56 sm:max-w-72 shadow-none hover:border-zinc-300 transition-colors">
								<SelectValue placeholder="Select Project" className="truncate">
									{selectedProjectName}
								</SelectValue>
							</SelectTrigger>
							<SelectContent
								align="end"
								alignItemWithTrigger={false}
								sideOffset={4}
								className="bg-white max-w-xs shadow-none"
							>
								<SelectItem value="none">
									<span className="truncate">No Project</span>
								</SelectItem>
								{projects.map((p) => (
									<SelectItem key={p.id} value={p.id}>
										<span className="truncate" title={p.name}>
											{p.name}
										</span>
									</SelectItem>
								))}
							</SelectContent>
						</Select>
					</div>
				) : isGeneralMode ? (
					<div className="flex items-center gap-1.5 text-xs text-zinc-600">
						<span>No files needed</span>
					</div>
				) : null}
			</div>

			{!isGeneralMode && (
				<div className="mt-4 px-3.5 py-1.5 w-fit mx-auto border border-zinc-200/60 rounded-md flex items-center justify-center text-[11px] text-zinc-600 bg-zinc-50/50">
					<RiFileTextLine className="size-3 mr-1.5 text-zinc-600" />
					Supports Text or PDF, DOCX, XLSX, TXT files
				</div>
			)}
		</>
	);
}
