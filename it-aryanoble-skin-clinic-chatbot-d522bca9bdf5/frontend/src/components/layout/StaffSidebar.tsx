"use client";

import * as React from "react";
import {
	Sidebar,
	SidebarContent,
	SidebarFooter,
	SidebarHeader,
	SidebarMenu,
	SidebarMenuButton,
	SidebarMenuItem,
	SidebarRail,
} from "@/components/ui/sidebar";
import { Button } from "@/components/ui/button";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { RiRobot2Line, RiFileAddLine } from "@remixicon/react";
import { SidebarProfileMenu } from "./sidebar-profile-menu";

import { useCurrentUser } from "@/hooks/use-current-user";

interface NavItem {
	title: string;
	url: string;
	iconSrc: string;
	requiredAccess: string | string[];
}

const staffNav: NavItem[] = [
	{
		title: "Knowledge Base",
		url: "/dashboard/knowledge",
		iconSrc: "/icons/database.png",
		requiredAccess: "knowledge:read",
	},
	{
		title: "Chat History",
		url: "/dashboard/chat-history",
		iconSrc: "/icons/history.png",
		requiredAccess: "chats:read",
	},
	{
		title: "Category",
		url: "/dashboard/category",
		iconSrc: "/icons/boxes.png",
		requiredAccess: "categories:read",
	},
	{
		title: "Branch",
		url: "/dashboard/branches",
		iconSrc: "/icons/store.png",
		requiredAccess: "branches:read",
	},
	{
		title: "User",
		url: "/dashboard/users",
		iconSrc: "/icons/user.png",
		requiredAccess: "users:read",
	},
	{
		title: "Roles",
		url: "/dashboard/roles",
		iconSrc: "/icons/user-cog.png",
		requiredAccess: ["roles:read", "users:read"],
	},
	{
		title: "Configuration",
		url: "/dashboard/configuration",
		iconSrc: "/icons/wrench.png",
		requiredAccess: ["configuration:read", "branches:read"],
	},
];

export function StaffSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
	const pathname = usePathname();
	const { data: user } = useCurrentUser();

	const userAccesses = user?.accesses || [];

	const visibleNav = staffNav.filter((item) => {
		if (Array.isArray(item.requiredAccess)) {
			return item.requiredAccess.some((acc) => userAccesses.includes(acc));
		}
		return userAccesses.includes(item.requiredAccess);
	});

	return (
		<Sidebar collapsible="icon" {...props} className="border-r border-border">
			<SidebarHeader className="px-4 pt-4 pb-0 group-data-[collapsible=icon]:p-2">
				<SidebarMenu>
					<SidebarMenuItem>
						<SidebarMenuButton
							size="lg"
							render={<Link href="/dashboard/knowledge" />}
							className="hover:bg-transparent hover:text-inherit active:bg-transparent cursor-default p-0 group-data-[collapsible=icon]:justify-center"
							tooltip="ERHA Medical Assistant"
						>
							<div className="flex aspect-square size-10 group-data-[collapsible=icon]:size-8 shrink-0 items-center justify-center rounded-md bg-blue-50 text-blue-700">
								<RiRobot2Line className="size-6 group-data-[collapsible=icon]:size-5 text-blue-700" />
							</div>
							<div className="flex flex-col gap-0.5 leading-none group-data-[collapsible=icon]:hidden overflow-hidden">
								<span className="font-semibold text-blue-700 text-sm whitespace-nowrap">
									ERHA Medical Assistant
								</span>
							</div>
						</SidebarMenuButton>
					</SidebarMenuItem>
				</SidebarMenu>
			</SidebarHeader>

			<SidebarContent>
				{userAccesses.includes("knowledge:write") && (
					<div className="px-4 pt-12 pb-2 group-data-[collapsible=icon]:p-2 group-data-[collapsible=icon]:pt-8">
						<Button
							render={<Link href="/dashboard/ingest" />}
							nativeButton={false}
							className="w-full justify-center bg-blue-600 hover:bg-blue-700 text-white shadow-none h-10 px-3 rounded-lg group-data-[collapsible=icon]:size-8 group-data-[collapsible=icon]:p-0 shrink-0 cursor-pointer"
						>
							<RiFileAddLine className="mr-2 size-5 group-data-[collapsible=icon]:mr-0 group-data-[collapsible=icon]:size-4 shrink-0" />
							<span className="font-medium text-sm group-data-[collapsible=icon]:hidden">
								Ingest Document
							</span>
						</Button>
					</div>
				)}
				<SidebarMenu className="px-3 mt-2 space-y-1 group-data-[collapsible=icon]:px-2">
					{visibleNav.map((item) => {
						const isActive = pathname === item.url || pathname.startsWith(item.url + "/");
						return (
							<SidebarMenuItem key={item.title}>
								<SidebarMenuButton
									isActive={isActive}
									render={<Link href={item.url} />}
									className={
										isActive ? "bg-blue-50 text-blue-600 hover:bg-blue-100" : "text-zinc-900"
									}
									tooltip={item.title}
								>
									<Image
										src={item.iconSrc}
										alt={item.title}
										width={16}
										height={16}
										className={`size-4 shrink-0 object-contain ${
											isActive ? "opacity-100" : "opacity-75"
										}`}
									/>
									<span className="font-medium">{item.title}</span>
								</SidebarMenuButton>
							</SidebarMenuItem>
						);
					})}
				</SidebarMenu>
			</SidebarContent>

			<SidebarFooter className="px-4 pb-4 pt-0 group-data-[collapsible=icon]:p-2">
				<SidebarProfileMenu />
			</SidebarFooter>

			<SidebarRail />
		</Sidebar>
	);
}
