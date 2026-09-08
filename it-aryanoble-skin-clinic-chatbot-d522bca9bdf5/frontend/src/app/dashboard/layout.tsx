import { SidebarProvider, SidebarInset } from "@/components/ui/sidebar";
import { Input } from "@/components/ui/input";
import { RiSearchLine } from "@remixicon/react";
import { RouteGuard } from "@/components/auth/route-guard";
import { StaffSidebar } from "@/components/layout/StaffSidebar";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
	return (
		<RouteGuard allowedTypes={["STAFF"]}>
			<SidebarProvider>
				<StaffSidebar />
				<SidebarInset className="bg-background">
					<header className="sticky top-0 z-10 flex shrink-0 items-center border-b p-4 bg-background">
						<div className="flex w-full max-w-md items-center relative">
							<RiSearchLine className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground size-4" />
							<Input
								type="search"
								placeholder="Search for clinical history, product, or treatment..."
								className="pl-9 bg-white"
							/>
						</div>
					</header>
					<div className="flex-1 overflow-auto relative">{children}</div>
				</SidebarInset>
			</SidebarProvider>
		</RouteGuard>
	);
}
