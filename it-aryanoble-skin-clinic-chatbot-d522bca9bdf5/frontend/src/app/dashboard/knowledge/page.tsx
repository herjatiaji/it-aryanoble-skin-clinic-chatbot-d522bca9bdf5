"use client";

import { useState } from "react";
import { KnowledgeSummary } from "./components/knowledge-summary";
import { ProjectsTable } from "./components/projects-table";
import { KnowledgeTable } from "./components/knowledge-table";
import { SearchBar } from "@/components/shared/search-bar";
import { useDebounce } from "@/hooks/use-debounce";

export default function KnowledgePage() {
	const [searchQuery, setSearchQuery] = useState("");
	const debouncedSearch = useDebounce(searchQuery, 300);

	return (
		<div className="flex flex-col w-full min-w-0 gap-6 p-6">
			{/* Overview Summary Cards */}
			<KnowledgeSummary />

			{/* Single Search Bar */}
			<div className="w-full">
				<SearchBar
					containerClassName="max-w-md w-full sm:w-80"
					value={searchQuery}
					onChange={(e) => setSearchQuery(e.target.value)}
					placeholder="Search for project or knowledge..."
				/>
			</div>

			{/* Section 1: Projects Table */}
			<ProjectsTable searchQuery={debouncedSearch} />

			{/* Section 2: All Knowledge Base Table */}
			<KnowledgeTable searchQuery={debouncedSearch} />
		</div>
	);
}
