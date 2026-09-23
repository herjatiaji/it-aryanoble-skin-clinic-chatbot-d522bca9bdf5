import { MarkdownContent } from "@/components/shared/markdown-content";
import {
	Attachment,
	AttachmentContent,
	AttachmentDescription,
	AttachmentMedia,
	AttachmentTitle,
} from "@/components/ui/attachment";
import { MessageScrollerItem } from "@/components/ui/message-scroller";
import { RiRobot2Line, RiUser3Line } from "@remixicon/react";
import { getAttachmentNames, getFileIconAndColor } from "../utils/chat-detail-utils";

interface ChatMessage {
	id?: string;
	role?: string;
	content: string;
	attachments?: Record<string, unknown> | null;
}

interface ChatDetailMessageItemProps {
	message: ChatMessage;
	isLast: boolean;
	index: number;
}

export function ChatDetailMessageItem({ message, isLast, index }: ChatDetailMessageItemProps) {
	const isUser = message.role?.toUpperCase() === "USER";
	const attachmentNames = getAttachmentNames(message.attachments, message.role);

	return (
		<MessageScrollerItem key={message.id || `msg-${index}`} scrollAnchor={isLast}>
			<div
				className={`flex flex-col w-full min-w-0 max-w-full ${isUser ? "items-end" : "items-start"}`}
			>
				{attachmentNames.length > 0 && (
					<div className={`flex flex-wrap gap-2 mb-2 ${isUser ? "justify-end" : "justify-start"}`}>
						{attachmentNames.map((name, i) => {
							const { Icon, bgColor, textColor } = getFileIconAndColor(name);
							return (
								<Attachment
									key={i}
									className="bg-white border border-zinc-200 shadow-none p-1.5 min-w-35 max-w-50 shrink-0 rounded-lg"
								>
									<AttachmentMedia className={`${bgColor} ${textColor} rounded-lg p-2 shrink-0`}>
										<Icon className="w-5 h-5" />
									</AttachmentMedia>
									<AttachmentContent className="overflow-hidden min-w-0 pr-2">
										<AttachmentTitle className="text-[13px] font-medium text-zinc-950 truncate block">
											{name}
										</AttachmentTitle>
										<AttachmentDescription className="text-[11px] text-zinc-500 uppercase">
											DOCUMENT
										</AttachmentDescription>
									</AttachmentContent>
								</Attachment>
							);
						})}
					</div>
				)}

				<div
					className={`flex items-start gap-3 w-full min-w-0 max-w-full ${isUser ? "flex-row-reverse" : ""}`}
				>
					<div className="bg-zinc-100 rounded text-zinc-950 flex items-center justify-center p-1.5 mt-0.5 shrink-0">
						{isUser ? <RiUser3Line className="size-4" /> : <RiRobot2Line className="size-4" />}
					</div>
					<div
						className={`${
							isUser
								? "bg-primary text-primary-foreground whitespace-pre-wrap max-w-[85%] sm:max-w-[75%] rounded-md"
								: "bg-transparent border border-zinc-200 text-zinc-950 w-full rounded-md"
						} p-3.5 text-sm min-w-0 overflow-hidden`}
					>
						{isUser ? message.content : <MarkdownContent content={message.content} />}
					</div>
				</div>
			</div>
		</MessageScrollerItem>
	);
}
