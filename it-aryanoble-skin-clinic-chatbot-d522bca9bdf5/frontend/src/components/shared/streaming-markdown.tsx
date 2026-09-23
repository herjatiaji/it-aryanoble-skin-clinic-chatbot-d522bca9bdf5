"use client";

import React, { useEffect, useState, useRef } from "react";
import { MarkdownContent } from "./markdown-content";

export interface StreamingMarkdownProps {
	content?: string;
	animate?: boolean;
	speed?: number; // ms per step
	wordsPerStep?: number;
	onFinished?: () => void;
	className?: string;
}

export function StreamingMarkdown({
	content = "",
	animate = false,
	speed = 18,
	wordsPerStep = 4,
	onFinished,
	className,
}: StreamingMarkdownProps) {
	const safeContent = content ?? "";
	const [displayedLength, setDisplayedLength] = useState(animate && safeContent ? 0 : safeContent.length);
	const [isStreaming, setIsStreaming] = useState(Boolean(animate && safeContent));
	const onFinishedRef = useRef(onFinished);

	useEffect(() => {
		onFinishedRef.current = onFinished;
	}, [onFinished]);

	useEffect(() => {
		if (!animate || !safeContent) {
			const timer = setTimeout(() => {
				setIsStreaming(false);
			}, 0);
			return () => clearTimeout(timer);
		}

		const initTimer = setTimeout(() => {
			setIsStreaming(true);
			setDisplayedLength(0);
		}, 0);

		// Split text by whitespace to stream word by word
		const words = safeContent.split(/(\s+)/);
		let currentWordIdx = 0;

		const interval = setInterval(() => {
			currentWordIdx = Math.min(words.length, currentWordIdx + wordsPerStep);
			const currentText = words.slice(0, currentWordIdx).join("");
			setDisplayedLength(currentText.length);

			if (currentWordIdx >= words.length) {
				clearInterval(interval);
				setIsStreaming(false);
				onFinishedRef.current?.();
			}
		}, speed);

		return () => {
			clearTimeout(initTimer);
			clearInterval(interval);
		};
	}, [safeContent, animate, speed, wordsPerStep]);

	const displayedText = animate && isStreaming ? safeContent.substring(0, displayedLength) : safeContent;

	return (
		<div className={className}>
			<MarkdownContent content={displayedText} />
			{animate && isStreaming && (
				<span
					className="inline-block w-1.5 h-4 ml-0.5 bg-blue-600 animate-pulse rounded-xs align-middle"
					aria-hidden="true"
				/>
			)}
		</div>
	);
}
