"use client";

import { useKnowledgeBaseList } from "@/app/dashboard/knowledge/hooks/use-knowledge";
import {
	RiDiscountPercentLine,
	RiMedicineBottleLine,
	RiRobot2Line,
	RiSyringeLine,
	RiArchiveLine,
} from "@remixicon/react";

export function KnowledgeSummary() {
	const { data: knowledgeList } = useKnowledgeBaseList();

	const totalCount = knowledgeList?.length ?? 0;
	const productCount = knowledgeList?.filter((k) => k.type === "PRODUCT").length ?? 0;
	const treatmentCount = knowledgeList?.filter((k) => k.type === "TREATMENT").length ?? 0;
	const promotionalCount = knowledgeList?.filter((k) => k.type === "PROMOTIONAL").length ?? 0;

	const summaries = [
		{
			title: "Total Knowledge",
			count: totalCount.toString(),
			icon: RiRobot2Line,
			iconColor: "text-blue-600",
			iconBg: "bg-blue-50",
		},
		{
			title: "Product Knowledge",
			count: productCount.toString(),
			icon: RiMedicineBottleLine,
			iconColor: "text-emerald-500",
			iconBg: "bg-emerald-50",
		},
		{
			title: "Treatment Knowledge",
			count: treatmentCount.toString(),
			icon: RiSyringeLine,
			iconColor: "text-rose-600",
			iconBg: "bg-rose-50",
		},
		{
			title: "Promotional",
			count: promotionalCount.toString(),
			icon: RiDiscountPercentLine,
			iconColor: "text-amber-500",
			iconBg: "bg-amber-50",
		},
		{
			title: "Other",
			count: (totalCount - productCount - treatmentCount - promotionalCount).toString(),
			icon: RiArchiveLine,
			iconColor: "text-purple-600",
			iconBg: "bg-purple-50",
		},
	];

	return (
		<div className="w-full">
			<div className="mb-4">
				<h2 className="text-xl font-semibold text-gray-900">Knowledge Base</h2>
				<p className="text-sm text-gray-500 mt-1">Here is the overview data of the ingestion</p>
			</div>
			<div className="flex border border-gray-200 rounded-md bg-white overflow-hidden">
				{summaries.map((item, index) => (
					<div
						key={index}
						className={`flex-1 flex items-center gap-4 p-4 ${
							index !== summaries.length - 1 ? "border-r border-gray-200" : ""
						}`}
					>
						<div className={`p-3 rounded-md ${item.iconBg}`}>
							<item.icon className={`w-6 h-6 ${item.iconColor}`} />
						</div>
						<div>
							<p className="text-sm text-gray-500">{item.title}</p>
							<p className="text-2xl font-medium text-gray-900 mt-1">{item.count}</p>
						</div>
					</div>
				))}
			</div>
		</div>
	);
}
