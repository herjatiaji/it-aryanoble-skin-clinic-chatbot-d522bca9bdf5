"use client";

import { Button } from "@/components/ui/button";
import {
	Sidebar,
	SidebarContent,
	SidebarFooter,
	SidebarHeader,
	SidebarRail,
} from "@/components/ui/sidebar";
import { RiCalendarLine, RiMessageAi3Line, RiSearchLine } from "@remixicon/react";
import Link from "next/link";
import * as React from "react";
import { SidebarProfileMenu } from "@/components/shared/SidebarProfileMenu";

import { useChatSessions } from "@/app/doctor/hooks/use-doctor-chat";

export function DoctorSidebar({ className, ...props }: React.ComponentProps<typeof Sidebar>) {
	const { data: sessions } = useChatSessions();

	const recentChats = sessions?.slice(0, 10) || [];

	return (
		<Sidebar collapsible="icon" className={`border-r border-border ${className || ""}`} {...props}>
			<SidebarHeader className="px-4 pt-4 pb-0 group-data-[collapsible=icon]:p-2">
				<Button
					nativeButton={false}
					render={<Link href="/doctor" />}
					className="w-full bg-blue-500 hover:bg-blue-600 text-white shadow-none h-10 px-3 rounded-md group-data-[collapsible=icon]:size-8 group-data-[collapsible=icon]:p-0 group-data-[collapsible=icon]:justify-center shrink-0"
				>
					<RiMessageAi3Line className="mr-2 size-4 group-data-[collapsible=icon]:mr-0 shrink-0" />
					<span className="font-medium text-sm group-data-[collapsible=icon]:hidden">New chat</span>
				</Button>
				<Button
					nativeButton={false}
					render={<Link href="/doctor/search" />}
					variant="ghost"
					className="w-full justify-start mt-2 shadow-none h-10 px-3 rounded-md text-zinc-950 hover:bg-zinc-100 group-data-[collapsible=icon]:size-8 group-data-[collapsible=icon]:p-0 group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:mt-2"
				>
					<RiSearchLine className="mr-2 size-4 group-data-[collapsible=icon]:mr-0 shrink-0" />
					<span className="font-medium text-sm group-data-[collapsible=icon]:hidden">
						Search chat
					</span>
				</Button>
				<h3 className="font-medium text-sm text-zinc-500 mt-6 mb-2 group-data-[collapsible=icon]:hidden">
					Recent Chat
				</h3>
			</SidebarHeader>

			<SidebarContent>
				<div className="px-4 pb-4 group-data-[collapsible=icon]:hidden">
					<div className="space-y-2">
						{recentChats.map((chat) => (
							<Link href={`/doctor/chat/${chat.id}`} key={chat.id} className="block">
								<div className="bg-transparent rounded-xl p-3 border border-gray-200 hover:border-gray-300 hover:bg-zinc-50 transition-colors">
									<p className="text-zinc-950 text-sm font-medium leading-snug truncate mb-2">
										{chat.query || "New Chat Session"}
									</p>
									<div className="flex items-center gap-4 mt-auto">
										<div className="flex items-center text-zinc-500">
											<RiCalendarLine className="size-4 mr-1 text-zinc-950" />
											<span className="text-xs">
												{new Date(chat.created_at).toLocaleDateString()}
											</span>
										</div>
										<div className="flex items-center text-zinc-500 ml-auto">
											<RiMessageAi3Line className="size-4 mr-1 text-zinc-950" />
											<span className="text-xs">{chat.messages || 0}</span>
										</div>
									</div>
								</div>
							</Link>
						))}

						{recentChats.length === 0 && (
							<div className="text-center p-4 border border-dashed border-gray-200 rounded-xl text-gray-500 text-sm">
								No recent chats
							</div>
						)}
					</div>
				</div>
			</SidebarContent>

			<SidebarFooter className="px-4 pb-4 pt-4 group-data-[collapsible=icon]:p-2 group-data-[collapsible=icon]:pb-2">
				{/* Chat Credit - Hidden until credit drops below a certain amount */}
				{false && (
					<div className="bg-blue-50/50 border border-blue-100 rounded-lg p-2.5 mb-4 group-data-[collapsible=icon]:hidden">
						<div className="flex items-center mb-1">
							<RiMessageAi3Line className="text-blue-500 size-3.5 mr-1.5" />
							<span className="text-blue-600 font-medium text-xs">25 Chat Credit Left</span>
						</div>
						<p className="text-zinc-500 text-[11px] leading-tight pl-5">
							Credit to initiate or follow up chat
						</p>
					</div>
				)}

				<SidebarProfileMenu />
			</SidebarFooter>

			<SidebarRail />
		</Sidebar>
	);
}
