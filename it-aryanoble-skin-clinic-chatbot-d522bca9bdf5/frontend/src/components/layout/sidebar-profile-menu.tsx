"use client";

import { useMemo } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
	RiArrowUpSLine,
	RiLogoutBoxRLine,
	RiNotification3Line,
} from "@remixicon/react";

import { useLogout } from "@/app/login/hooks/use-logout";
import { NOTIFICATION_KEYS } from "@/app/dashboard/notifications/api/keys";
import { FeedbackNotification } from "@/app/dashboard/notifications/api/types";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
	DropdownMenu,
	DropdownMenuContent,
	DropdownMenuItem,
	DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
	SidebarMenu,
	SidebarMenuButton,
	SidebarMenuItem,
	useSidebar,
} from "@/components/ui/sidebar";
import { useCurrentUser } from "@/hooks/use-current-user";
import { api } from "@/lib/axios";

export function SidebarProfileMenu() {
	const pathname = usePathname();
	const { mutate: logout, isPending: isLoggingOut } = useLogout();
	const { data: user } = useCurrentUser();
	const { state } = useSidebar();
	const isCollapsed = state === "collapsed";

	const isNotificationsActive =
		pathname === "/dashboard/notifications" ||
		pathname.startsWith("/dashboard/notifications/");

	const { data: feedbacks = [] } = useQuery<FeedbackNotification[]>({
		queryKey: NOTIFICATION_KEYS.lists(),
		queryFn: async () => {
			const res = await api.get("/chats/feedback");
			return res.data;
		},
	});

	const unreadCount = useMemo(
		() => feedbacks.filter((f) => !f.is_feedback_read).length,
		[feedbacks],
	);

	const userName = user?.name || "User";
	const userRole = user?.roles?.[0]?.name || "Staff";
	const initials =
		userName
			.split(" ")
			.map((n: string) => n[0])
			.join("")
			.toUpperCase()
			.substring(0, 2) || "U";

	return (
		<SidebarMenu className="gap-2 group-data-[collapsible=icon]:gap-1">
			<SidebarMenuItem>
				<SidebarMenuButton
					isActive={isNotificationsActive}
					render={<Link href="/dashboard/notifications" />}
					className={
						isNotificationsActive
							? "bg-blue-50 text-blue-600 hover:bg-blue-100"
							: "text-zinc-900"
					}
					tooltip={unreadCount > 0 ? `Notifications (${unreadCount} unread)` : "Notifications"}
				>
					<div className="relative flex items-center justify-center">
						<RiNotification3Line
							className={`size-4 shrink-0 ${
								isNotificationsActive ? "text-blue-600" : "text-zinc-500"
							}`}
						/>
						{unreadCount > 0 && (
							<span className="absolute -top-1 -right-1 size-2 rounded-full bg-red-500 ring-2 ring-white group-data-[collapsible=icon]:block hidden" />
						)}
					</div>
					<span className="font-medium group-data-[collapsible=icon]:hidden">Notifications</span>
					{unreadCount > 0 && (
						<span className="ml-auto inline-flex items-center justify-center min-w-5 h-5 px-1 rounded-sm bg-red-50 text-red-600 border border-red-200 font-semibold text-[10.5px] leading-none tabular-nums select-none shrink-0 group-data-[collapsible=icon]:hidden">
							{unreadCount > 99 ? "99+" : unreadCount}
						</span>
					)}
				</SidebarMenuButton>
			</SidebarMenuItem>
			<SidebarMenuItem className="mt-1 group-data-[collapsible=icon]:mt-0">
				<DropdownMenu>
					<DropdownMenuTrigger
						className="h-auto py-2 px-2.5 hover:bg-zinc-100 active:bg-zinc-200 cursor-pointer rounded-lg flex items-center justify-between w-full group-data-[collapsible=icon]:p-0 group-data-[collapsible=icon]:size-8 group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:mx-auto data-popup-open:bg-zinc-100 outline-none text-left transition-colors border-0 bg-transparent"
					>
						<div className="flex items-center gap-2.5 overflow-hidden flex-1 min-w-0 group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:flex-none">
							<Avatar className="size-9 shrink-0 group-data-[collapsible=icon]:size-8 rounded-md after:rounded-md">
								<AvatarFallback className="rounded-md bg-blue-50 text-blue-600 font-semibold text-xs border border-blue-100">
									{initials}
								</AvatarFallback>
							</Avatar>
							<div className="flex flex-col gap-0.5 text-left group-data-[collapsible=icon]:hidden overflow-hidden flex-1 min-w-0">
								<span className="font-medium text-zinc-900 text-xs truncate">
									{userName}
								</span>
								<span className="text-[11px] text-zinc-500 truncate capitalize">
									{userRole.toLowerCase()}
								</span>
							</div>
						</div>
						<RiArrowUpSLine className="size-4 text-zinc-400 shrink-0 group-data-[collapsible=icon]:hidden ml-1 transition-transform group-data-[state=open]:rotate-180" />
					</DropdownMenuTrigger>
					<DropdownMenuContent
						side={isCollapsed ? "right" : "top"}
						align={isCollapsed ? "end" : "center"}
						sideOffset={isCollapsed ? 12 : 6}
						className={
							isCollapsed
								? "w-36 rounded-md p-1 shadow-md border border-gray-200 bg-white z-50"
								: "w-(--anchor-width) min-w-40 rounded-md p-1 shadow-none border border-gray-200 bg-white z-50"
						}
					>
						<DropdownMenuItem
							onClick={() => logout()}
							disabled={isLoggingOut}
							variant="destructive"
							className="cursor-pointer text-red-600 hover:bg-red-50 hover:text-red-700 rounded px-2.5 py-2 text-xs font-medium gap-2 flex items-center transition-colors w-full"
						>
							<RiLogoutBoxRLine className="size-4 text-red-500 shrink-0" />
							<span>{isLoggingOut ? "Logging out..." : "Log out"}</span>
						</DropdownMenuItem>
					</DropdownMenuContent>
				</DropdownMenu>
			</SidebarMenuItem>
		</SidebarMenu>
	);
}
