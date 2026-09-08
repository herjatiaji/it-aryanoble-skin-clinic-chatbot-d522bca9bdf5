"use client";

import { PromptInput } from "@/components/shared/prompt-input";
import {
	RiFileTextLine,
	RiMedicineBottleLine,
	RiRobot2Line,
	RiSyringeLine,
} from "@remixicon/react";
import { useCreateChatSession } from "./hooks/use-doctor-chat";

export default function DoctorChatPage() {
	const createChat = useCreateChatSession();
	const handleSend = (text: string, category: string | undefined, files: File[]) => {
		if (!text.trim() && files.length === 0) return;

		const formData = new FormData();
		formData.append("role", "USER");
		formData.append("content", text || "Attached file(s)");
		files.forEach((f) => formData.append("files", f));

		createChat.mutate({ branch_id: null, initialMessageFormData: formData });
	};

	const handleShortcut = (shortcut: string) => {
		const formData = new FormData();
		formData.append("role", "USER");
		formData.append("content", shortcut);
		createChat.mutate({ branch_id: null, initialMessageFormData: formData });
	};

	const formattedDate = new Intl.DateTimeFormat("en-US", {
		weekday: "long",
		month: "2-digit",
		day: "2-digit",
		year: "numeric",
	}).format(new Date());

	return (
		<div className="flex flex-col max-w-2xl mx-auto min-h-full w-full pt-10 pb-10 px-4">
			{/* Date */}
			<div className="text-[13px] font-medium text-zinc-500 mb-6 text-center">{formattedDate}</div>

			{/* Header */}
			<div className="flex flex-col items-center text-center space-y-2 mb-8">
				<div className="flex aspect-square size-12 items-center justify-center rounded-md bg-blue-50 text-blue-500">
					<RiRobot2Line className="size-6" />
				</div>
				<div className="space-y-1">
					<h1 className="text-lg font-semibold tracking-tight text-zinc-950">
						Hello Doctor, I&apos;m Ready to Help!
					</h1>
					<p className="text-[13px] text-zinc-500 max-w-lg leading-relaxed mx-auto">
						Tell me about the patient&apos;s concerns and background, and I&apos;ll suggest the best
						treatment or product for them at ERHA Medical.
					</p>
				</div>
			</div>

			{/* Shortcuts */}
			<div className="grid grid-cols-2 gap-3 w-full mb-4 shrink-0">
				<button
					disabled={createChat.isPending}
					onClick={() => handleShortcut("Can you suggest a product for this condition...")}
					className="flex flex-col items-start p-2.5 text-left rounded-md border border-border hover:border-zinc-300 hover:bg-zinc-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
				>
					<RiMedicineBottleLine className="size-4 text-zinc-950 mb-1.5" />
					<h3 className="font-semibold text-xs text-zinc-950 mb-0.5">Product Recomendation</h3>
					<p className="text-[11px] leading-tight text-zinc-500">
						Can you suggest a product for this condition...
					</p>
				</button>
				<button
					disabled={createChat.isPending}
					onClick={() => handleShortcut("Could you recommend a treatment for this condition...")}
					className="flex flex-col items-start p-2.5 text-left rounded-md border border-border hover:border-zinc-300 hover:bg-zinc-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
				>
					<RiSyringeLine className="size-4 text-zinc-950 mb-1.5" />
					<h3 className="font-semibold text-xs text-zinc-950 mb-0.5">Treatment Recomendation</h3>
					<p className="text-[11px] leading-tight text-zinc-500">
						Could you recommend a treatment for this condition...
					</p>
				</button>
			</div>

			<div className="shrink-0 mt-4 flex flex-col items-center">
				<div className="w-full relative">
					{createChat.isPending && (
						<div className="absolute inset-0 z-10 bg-white/50 flex items-center justify-center rounded-md">
							<span className="text-sm text-zinc-500">Starting chat...</span>
						</div>
					)}
					<PromptInput
						minRows={3}
						hideCategories
						showAttachText
						placeholder="Can you suggest a product for this condition..."
						onSend={handleSend}
					/>
				</div>
				<div className="mt-3 px-4 w-fit mx-auto border border-zinc-200 rounded-md p-2.5 flex items-center justify-center text-xs text-zinc-500 bg-white">
					<RiFileTextLine className="size-3 mr-2 text-zinc-400" />
					File format including PDF, docx, excel, image
				</div>
			</div>
		</div>
	);
}
