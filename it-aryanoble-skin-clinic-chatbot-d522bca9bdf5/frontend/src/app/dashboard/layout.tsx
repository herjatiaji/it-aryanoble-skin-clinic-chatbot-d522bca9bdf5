import { RouteGuard } from "@/components/auth";
import { StaffSidebar } from "@/components/layout/StaffSidebar";
import { CisSyncListener } from "@/components/layout/cis-sync-listener";
import { DashboardHeader } from "@/components/layout/dashboard-header";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
	return (
		<RouteGuard allowedTypes={["STAFF"]}>
			<SidebarProvider>
				<CisSyncListener />
				<StaffSidebar />
				<SidebarInset className="bg-background min-w-0 overflow-x-hidden">
					<DashboardHeader />
					<div className="flex-1 min-w-0 relative">{children}</div>
				</SidebarInset>
			</SidebarProvider>
		</RouteGuard>
	);
}
