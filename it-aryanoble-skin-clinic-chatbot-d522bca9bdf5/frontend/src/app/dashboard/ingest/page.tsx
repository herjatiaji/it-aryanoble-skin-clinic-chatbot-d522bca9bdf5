"use client";

import { PromptInput } from "@/components/shared/prompt-input";
import {
	RiFileTextLine,
	RiMedicineBottleLine,
	RiRobot2Line,
	RiSyringeLine,
} from "@remixicon/react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { RiAlertLine } from "@remixicon/react";
import { useUploadKnowledge } from "../knowledge/hooks/use-knowledge";

export default function IngestPage() {
	const router = useRouter();
	const uploadMutation = useUploadKnowledge();

	const [errorMsg, setErrorMsg] = useState<string | null>(null);

	const handleSend = (value: string, category: string | undefined, files: File[]) => {
		if (files.length === 0) {
			setErrorMsg("Please attach at least one file to ingest.");
			return false;
		}

		if (!category) {
			setErrorMsg("Please select a category (Product, Treatment, Promotional, or Other).");
			return false;
		}

		setErrorMsg(null);

		const formData = new FormData();
		if (value) {
			formData.append("prompt", value);
		}
		formData.append("category_type", category.toUpperCase());

		files.forEach((file) => {
			formData.append("files", file);
		});

		uploadMutation.mutate(formData, {
			onSuccess: (data) => {
				if (data?.knowledge_ids && data.knowledge_ids.length > 1) {
					router.push("/dashboard/knowledge");
				} else if (data?.knowledge_id) {
					router.push(`/dashboard/knowledge/${data.knowledge_id}`);
				} else {
					router.push("/dashboard/knowledge");
				}
			},
		});
	};

	return (
		<div className="flex flex-col max-w-2xl mx-auto min-h-full w-full pt-10 pb-10 px-4">
			{/* Header */}
			<div className="flex flex-col items-center text-center space-y-2 mb-8">
				<div className="flex aspect-square size-12 items-center justify-center rounded-md bg-blue-50 text-blue-500">
					<RiRobot2Line className="size-6" />
				</div>
				<div className="space-y-1">
					<h1 className="text-lg font-semibold tracking-tight text-zinc-950">
						Expand our clinical knowledge today
					</h1>
					<p className="text-[13px] text-zinc-500 max-w-95 leading-relaxed">
						Ingesting documents to train the ai erha knowledge with product, treatment, and
						promotional brochure
					</p>
				</div>
			</div>
			{/* Shortcuts */}
			<div className="grid grid-cols-2 gap-3 w-full mb-4 shrink-0">
				<button className="flex flex-col items-start p-2.5 text-left rounded-md border border-border hover:border-zinc-300 hover:bg-zinc-50 transition-colors">
					<RiMedicineBottleLine className="size-4 text-zinc-950 mb-1.5" />
					<h3 className="font-semibold text-xs text-zinc-950 mb-0.5">Product Knowledge</h3>
					<p className="text-[11px] leading-tight text-zinc-500">
						Can you suggest a product for this condition...
					</p>
				</button>
				<button className="flex flex-col items-start p-2.5 text-left rounded-md border border-border hover:border-zinc-300 hover:bg-zinc-50 transition-colors">
					<RiSyringeLine className="size-4 text-zinc-950 mb-1.5" />
					<h3 className="font-semibold text-xs text-zinc-950 mb-0.5">Treatment Recomendation</h3>
					<p className="text-[11px] leading-tight text-zinc-500">
						Could you recommend a treatment for this condition...
					</p>
				</button>
			</div>

			{/* Prompt Input */}
			<div className="shrink-0 mt-4 flex flex-col items-center relative">
				<div className="w-full">
					<PromptInput minRows={3} onSend={handleSend} />
				</div>

				{errorMsg && (
					<div className="w-full mt-2 flex items-center text-[13px] font-medium text-amber-600 bg-amber-50 border border-amber-200 rounded-md p-2.5">
						<RiAlertLine className="size-4 mr-1.5 shrink-0" />
						{errorMsg}
					</div>
				)}

				{uploadMutation.isPending && (
					<div className="absolute inset-0 bg-white/50 flex items-center justify-center rounded-md z-10 backdrop-blur-sm">
						<span className="text-sm font-medium text-blue-600">Uploading documents...</span>
					</div>
				)}

				<div className="mt-3 px-4 w-fit mx-auto border border-zinc-200 rounded-xl p-2.5 flex items-center justify-center text-xs text-zinc-500 bg-white">
					<RiFileTextLine className="size-3 mr-2 text-zinc-400" />
					File format including PDF, docx, excel, image
				</div>
			</div>
		</div>
	);
}
