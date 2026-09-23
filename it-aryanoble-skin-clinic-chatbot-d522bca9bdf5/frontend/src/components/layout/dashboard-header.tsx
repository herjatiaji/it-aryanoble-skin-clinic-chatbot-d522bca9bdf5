"use client";

import { GlobalSearchBar } from "@/components/layout/global-search-bar";

export function DashboardHeader() {
	return (
		<header className="sticky top-0 z-30 flex shrink-0 items-center border-b p-4 bg-background">
			<GlobalSearchBar />
		</header>
	);
}
