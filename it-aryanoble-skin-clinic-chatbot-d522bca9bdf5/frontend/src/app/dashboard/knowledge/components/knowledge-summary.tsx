"use client";

import { useKnowledgeBaseList } from "@/app/dashboard/knowledge/hooks/use-knowledge";
import { useProjectStats } from "@/app/dashboard/knowledge/hooks/use-projects";
import { RiRobot2Line, RiBookOpenLine } from "@remixicon/react";

export function KnowledgeSummary() {
	const { data: stats } = useProjectStats();
	const { data: knowledgeList } = useKnowledgeBaseList();

	const totalProjects = stats?.total_projects ?? 0;
	const totalKnowledge = stats?.total_knowledge ?? (knowledgeList?.length ?? 0);

	const summaries = [
		{
			title: "Total Projects",
			count: totalProjects.toString(),
			icon: RiBookOpenLine,
			iconColor: "text-emerald-500",
			iconBg: "bg-emerald-50",
		},
		{
			title: "Total Knowledge",
			count: totalKnowledge.toString(),
			icon: RiRobot2Line,
			iconColor: "text-blue-600",
			iconBg: "bg-blue-50",
		},
	];

	return (
		<div className="w-full">
			<div className="mb-4">
				<h1 className="text-xl font-semibold text-foreground">Knowledge Base</h1>
				<p className="text-sm text-muted-foreground mt-1">Here is the overview data of the ingestion</p>
			</div>
			<div className="inline-flex border border-gray-200 rounded-md bg-white overflow-hidden shadow-none">
				{summaries.map((item, index) => (
					<div
						key={index}
						className={`w-64 flex items-center gap-4 p-4 ${
							index !== summaries.length - 1 ? "border-r border-gray-200" : ""
						}`}
					>
						<div className={`p-3 rounded-md ${item.iconBg}`}>
							<item.icon className={`w-6 h-6 ${item.iconColor}`} />
						</div>
						<div>
							<p className="text-sm text-zinc-600">{item.title}</p>
							<p className="text-2xl font-medium text-gray-900 mt-1">{item.count}</p>
						</div>
					</div>
				))}
			</div>
		</div>
	);
}
