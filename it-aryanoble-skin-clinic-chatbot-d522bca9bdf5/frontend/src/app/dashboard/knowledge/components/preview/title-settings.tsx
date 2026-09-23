import { RiBookReadLine, RiEdit2Line } from "@remixicon/react";
import { useState, useRef, useEffect } from "react";

interface TitleSettingsProps {
	title: string;
	onChangeTitle: (newTitle: string) => void;
	isEditMode?: boolean;
	onCancel?: () => void;
}

export function TitleSettings({ title, onChangeTitle, isEditMode = false }: TitleSettingsProps) {
	const [localTitle, setLocalTitle] = useState(title);
	const [isLocalEditing, setIsLocalEditing] = useState(false);
	const [prevTitle, setPrevTitle] = useState(title);
	const inputRef = useRef<HTMLInputElement>(null);

	if (title !== prevTitle) {
		setPrevTitle(title);
		setLocalTitle(title);
	}

	useEffect(() => {
		if (isLocalEditing && inputRef.current) {
			inputRef.current.focus();
		}
	}, [isLocalEditing]);

	const handleSave = () => {
		setIsLocalEditing(false);
		onChangeTitle(localTitle);
	};

	const handleCancel = () => {
		setIsLocalEditing(false);
		setLocalTitle(title);
	};

	if (isLocalEditing) {
		return (
			<div className="flex items-center gap-2 w-fit max-w-full">
				<div className="flex items-center gap-2 h-9 px-3 border border-zinc-200 rounded-lg bg-white transition-colors flex-1 min-w-0 overflow-hidden">
					<RiBookReadLine className="size-4 text-zinc-400 shrink-0" />
					<div className="relative inline-grid items-center min-w-0 overflow-hidden flex-1">
						<span className="invisible whitespace-pre text-xs font-medium col-start-1 row-start-1 pr-1 truncate">
							{localTitle || " "}
						</span>
						<input 
							ref={inputRef}
							className="text-xs font-medium text-zinc-950 outline-none w-full bg-transparent col-start-1 row-start-1 min-w-0"
							value={localTitle}
							onChange={(e) => setLocalTitle(e.target.value)}
							onBlur={handleSave}
							onKeyDown={(e) => {
								if (e.key === 'Enter') handleSave();
								if (e.key === 'Escape') handleCancel();
							}}
						/>
					</div>
				</div>
				<button 
					type="button"
					onMouseDown={(e) => {
						e.preventDefault();
						handleCancel();
					}} 
					className="h-9 px-3.5 text-xs font-medium border border-zinc-200 bg-white text-zinc-700 rounded-lg hover:bg-zinc-50 transition-colors shrink-0 cursor-pointer shadow-none"
				>
					Cancel
				</button>
				<button 
					type="button"
					onMouseDown={(e) => {
						e.preventDefault();
						handleSave();
					}} 
					className="h-9 px-3.5 text-xs font-medium bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors shrink-0 cursor-pointer shadow-none"
				>
					Save
				</button>
			</div>
		);
	}

	return (
		<div className="flex items-center gap-2 w-fit max-w-full">
			<div className="flex items-center gap-2 h-9 px-3 border border-zinc-200 rounded-lg bg-white flex-1 min-w-0 overflow-hidden">
				<RiBookReadLine className="size-4 text-zinc-900 shrink-0" />
				<span className="text-xs font-medium text-zinc-950 truncate min-w-0">{localTitle}</span>
			</div>
			{isEditMode && (
				<button 
					type="button"
					onClick={() => setIsLocalEditing(true)} 
					className="size-9 flex items-center justify-center border border-zinc-200 rounded-lg bg-white hover:bg-zinc-50 transition-colors text-zinc-700 shrink-0 cursor-pointer shadow-none"
					title="Edit title"
					aria-label="Edit title"
				>
					<RiEdit2Line className="size-4" />
				</button>
			)}
		</div>
	);
}
