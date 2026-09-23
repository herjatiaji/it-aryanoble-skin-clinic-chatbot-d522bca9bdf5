"use client";

import { useState, useEffect, useMemo } from "react";
import { toast } from "sonner";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field, FieldLabel, FieldContent } from "@/components/ui/field";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import { useProjects, useCreateProject } from "../hooks/use-projects";
import { useUpdateKnowledgeProject } from "../hooks/use-knowledge";
import { RiAddLine, RiLoader4Line } from "@remixicon/react";

interface AttachProjectDialogProps {
	isOpen: boolean;
	onClose: () => void;
	knowledgeId: string | null;
	knowledgeIds?: string[];
	knowledgeTitle?: string;
	currentProjectId?: string | null;
}

export function AttachProjectDialog({
	isOpen,
	onClose,
	knowledgeId,
	knowledgeIds,
	currentProjectId = null,
}: AttachProjectDialogProps) {
	const { data: projects = [], isLoading: isLoadingProjects } = useProjects();
	const updateKnowledgeProjectMutation = useUpdateKnowledgeProject();
	const createProjectMutation = useCreateProject();

	const [selectedProjectId, setSelectedProjectId] = useState<string>("none");
	const [isCreatingProject, setIsCreatingProject] = useState(false);
	const [newProjectName, setNewProjectName] = useState("");
	const [createError, setCreateError] = useState<string | null>(null);

	const isSubmitting =
		createProjectMutation.isPending || updateKnowledgeProjectMutation.isPending;

	const selectedProjectName = useMemo(() => {
		if (!selectedProjectId || selectedProjectId === "none") {
			return "No Project";
		}
		const found = projects.find((p) => p.id === selectedProjectId);
		return found ? found.name : "Select Project";
	}, [selectedProjectId, projects]);

	useEffect(() => {
		const timer = setTimeout(() => {
			if (isOpen) {
				setIsCreatingProject(false);
				setNewProjectName("");
				setCreateError(null);
				if (!currentProjectId || currentProjectId === "none") {
					setSelectedProjectId("none");
				} else {
					setSelectedProjectId(currentProjectId);
				}
			} else {
				setIsCreatingProject(false);
				setNewProjectName("");
				setCreateError(null);
			}
		}, 0);
		return () => clearTimeout(timer);
	}, [isOpen, currentProjectId]);

	const handleSubmit = async (e: React.FormEvent) => {
		e.preventDefault();

		let targetProjectId: string | null = null;

		if (isCreatingProject) {
			if (!newProjectName.trim()) {
				setCreateError("Project name is required.");
				return;
			}
			try {
				const newProj = await createProjectMutation.mutateAsync({
					name: newProjectName.trim(),
				});
				targetProjectId = newProj.id;
			} catch {
				return; // Handled by mutation error toast
			}
		} else {
			const isValidProject =
				selectedProjectId !== "none" &&
				projects.some((p) => p.id === selectedProjectId);
			targetProjectId = isValidProject ? selectedProjectId : null;
		}

		const idsToUpdate =
			knowledgeIds && knowledgeIds.length > 0
				? knowledgeIds
				: knowledgeId
					? [knowledgeId]
					: [];
		if (idsToUpdate.length === 0) return;

		try {
			if (idsToUpdate.length > 1) {
				await Promise.all(
					idsToUpdate.map((id) =>
						updateKnowledgeProjectMutation.mutateAsync({
							knowledgeId: id,
							projectId: targetProjectId,
							hideToast: true,
						}),
					),
				);
				const actionText = targetProjectId
					? "attached to project"
					: "detached from project";
				toast.success(
					`All ${idsToUpdate.length} documents ${actionText} successfully!`,
				);
			} else {
				await updateKnowledgeProjectMutation.mutateAsync({
					knowledgeId: idsToUpdate[0],
					projectId: targetProjectId,
				});
			}
			onClose();
		} catch {
			// handled by mutation
		}
	};

	return (
		<Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
			<DialogContent className="sm:max-w-md w-full bg-white p-6 rounded-lg border border-gray-200 shadow-none">
				<form onSubmit={handleSubmit} className="space-y-4">
					<DialogHeader className="p-0 pb-1">
						<DialogTitle className="text-base font-semibold text-foreground">
							Attach Knowledge to Project
						</DialogTitle>
						<DialogDescription className="text-xs text-muted-foreground">
							Assign knowledge to a project workspace.
						</DialogDescription>
					</DialogHeader>

					<Field className="space-y-2">
						<div className="flex items-center justify-between">
							<FieldLabel className="text-xs font-medium text-zinc-700">
								{isCreatingProject ? "New Project Name" : "Project"}
							</FieldLabel>
							{isCreatingProject ? (
								<button
									type="button"
									onClick={() => {
										setIsCreatingProject(false);
										setNewProjectName("");
										setCreateError(null);
									}}
									className="text-xs text-blue-600 hover:text-blue-700 font-medium cursor-pointer transition-colors"
								>
									Choose existing project
								</button>
							) : (
								<button
									type="button"
									onClick={() => {
										setIsCreatingProject(true);
										setCreateError(null);
									}}
									className="inline-flex items-center gap-1 text-xs font-medium text-blue-600 hover:text-blue-700 transition-colors cursor-pointer"
								>
									<RiAddLine className="size-3.5" />
									<span>New Project</span>
								</button>
							)}
						</div>

						<FieldContent>
							{isCreatingProject ? (
								<div className="space-y-1.5">
									<Input
										autoFocus
										autoComplete="off"
										placeholder="e.g. ERHA Acne Treatment"
										value={newProjectName}
										onChange={(e) => {
											setNewProjectName(e.target.value);
											if (createError) setCreateError(null);
										}}
										disabled={isSubmitting}
										className="h-10 border-gray-200 bg-white text-sm focus-visible:ring-blue-500 rounded-lg"
									/>
									{createError && (
										<p className="text-xs font-medium text-red-600">
											{createError}
										</p>
									)}
								</div>
							) : (
								<Select
									value={selectedProjectId}
									onValueChange={(val) => {
										if (val === "__create_new__") {
											setIsCreatingProject(true);
											setCreateError(null);
										} else {
											setSelectedProjectId(val ?? "none");
										}
									}}
									disabled={isLoadingProjects || isSubmitting}
								>
									<SelectTrigger className="w-full h-10 border-gray-200 bg-white text-gray-700 rounded-lg px-3">
										<SelectValue placeholder="Select Project">
											{selectedProjectName}
										</SelectValue>
									</SelectTrigger>
									<SelectContent
										alignItemWithTrigger={false}
										sideOffset={4}
										className="bg-white"
									>
										<SelectItem
											value="__create_new__"
											className="text-blue-600 font-medium hover:bg-blue-50 focus:bg-blue-50 focus:text-blue-700 cursor-pointer"
										>
											<div className="flex items-center gap-1.5">
												<RiAddLine className="size-4" />
												<span>Create new project...</span>
											</div>
										</SelectItem>
										<SelectItem value="none">No Project</SelectItem>
										{projects.map((project) => (
											<SelectItem key={project.id} value={project.id}>
												{project.name}
											</SelectItem>
										))}
									</SelectContent>
								</Select>
							)}
						</FieldContent>
					</Field>

					<DialogFooter className="flex items-center justify-end gap-3 pt-4 border-t-0 p-0">
						<Button
							type="button"
							variant="outline"
							onClick={() => {
								if (isCreatingProject) {
									setIsCreatingProject(false);
									setNewProjectName("");
									setCreateError(null);
								} else {
									onClose();
								}
							}}
							disabled={isSubmitting}
							className="border-gray-200 bg-white text-zinc-700 hover:bg-zinc-50 rounded-lg px-4 h-10 font-medium text-sm transition-colors cursor-pointer shadow-none"
						>
							{isCreatingProject ? "Back" : "Cancel"}
						</Button>
						<Button
							type="submit"
							disabled={
								isSubmitting ||
								isLoadingProjects ||
								(isCreatingProject && !newProjectName.trim())
							}
							className="h-10 px-4 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium cursor-pointer shadow-none gap-2"
						>
							{isSubmitting && (
								<RiLoader4Line className="size-4 animate-spin" />
							)}
							<span>
								{isCreatingProject
									? "Create & Attach"
									: "Attach Knowledge"}
							</span>
						</Button>
					</DialogFooter>
				</form>
			</DialogContent>
		</Dialog>
	);
}
