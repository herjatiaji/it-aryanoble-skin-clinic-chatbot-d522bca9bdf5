"use client";

import { useLogout } from "@/app/login/hooks/use-logout";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { SidebarMenu, SidebarMenuButton, SidebarMenuItem } from "@/components/ui/sidebar";
import { useCurrentUser } from "@/hooks/use-current-user";
import { RiLogoutBoxRLine, RiNotification3Line } from "@remixicon/react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Separator } from "../ui/separator";

export function SidebarProfileMenu() {
	const { mutate: logout, isPending: isLoggingOut } = useLogout();
	const { data: user } = useCurrentUser();
	const pathname = usePathname();

	const isDoctor = pathname?.startsWith("/doctor");

	const userName = user?.name || "User";
	const userRole = user?.roles?.[0]?.name || "User";
	const initials =
		userName
			.split(" ")
			.map((n: string) => n[0])
			.join("")
			.toUpperCase()
			.substring(0, 2) || "U";

	return (
		<SidebarMenu>
			{!isDoctor && (
				<>
					<SidebarMenuItem>
						<SidebarMenuButton
							render={<Link href="/dashboard/notifications" />}
							className="text-zinc-500 hover:text-blue-600 hover:bg-blue-50"
							tooltip="Notifications"
						>
							<RiNotification3Line className="size-4" />
							<span className="font-medium group-data-[collapsible=icon]:hidden">Notifications</span>
						</SidebarMenuButton>
					</SidebarMenuItem>
					<Separator className="my-3" />
				</>
			)}
			<SidebarMenuItem className="flex items-center flex-row group-data-[collapsible=icon]:justify-center">
				<SidebarMenuButton
					size="lg"
					className="h-auto min-h-12 py-1 hover:bg-transparent hover:text-inherit active:bg-transparent cursor-default p-0 flex-1 group-data-[collapsible=icon]:flex-none group-data-[collapsible=icon]:justify-center"
				>
					<Avatar className="size-10 shrink-0 group-data-[collapsible=icon]:size-8 rounded-md after:rounded-md">
						<AvatarFallback className="rounded-md">{initials}</AvatarFallback>
					</Avatar>
					<div className="flex flex-col gap-1 ml-2 group-data-[collapsible=icon]:hidden">
						<span className="font-semibold text-zinc-900 text-xs whitespace-normal wrap-break-word text-left">
							{userName}
						</span>
						<span className="text-[10px] text-zinc-500 whitespace-normal wrap-break-word text-left capitalize">
							{userRole.toLowerCase()}
						</span>
					</div>
				</SidebarMenuButton>
			</SidebarMenuItem>
			<Separator className="my-3" />
			<SidebarMenuItem>
				<SidebarMenuButton
					onClick={() => logout()}
					disabled={isLoggingOut}
					className="text-zinc-500 hover:text-red-600 hover:bg-red-50"
					tooltip="Logout"
				>
					<RiLogoutBoxRLine className="size-4" />
					<span className="font-medium group-data-[collapsible=icon]:hidden">Logout</span>
				</SidebarMenuButton>
			</SidebarMenuItem>
		</SidebarMenu>
	);
}
