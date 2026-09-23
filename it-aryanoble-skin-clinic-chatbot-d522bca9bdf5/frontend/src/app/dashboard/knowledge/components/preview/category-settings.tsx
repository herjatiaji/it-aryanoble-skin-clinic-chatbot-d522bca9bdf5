import { useCategories } from "@/app/dashboard/category/hooks/use-categories";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

import { RiCloseLine, RiSparklingLine, RiEdit2Line } from "@remixicon/react";
import { useRef, useState } from "react";

interface CategorySettingsProps {
	categories: string[];
	onChangeCategories: (newCategories: string[]) => void;
	isEditMode?: boolean;
	showSaveActions?: boolean;
}

export function CategorySettings({
	categories,
	onChangeCategories,
	isEditMode = false,
	showSaveActions = true,
}: CategorySettingsProps) {
	const { data: allCategories = [] } = useCategories();
	const [inputValue, setInputValue] = useState("");
	const [open, setOpen] = useState(false);
	const [isEditing, setIsEditing] = useState(isEditMode);
	const inputRef = useRef<HTMLInputElement>(null);

	const [prevIsEditMode, setPrevIsEditMode] = useState(isEditMode);

	// Local staging state
	const [localCategories, setLocalCategories] = useState<string[]>(categories);
	const [backupCategories, setBackupCategories] = useState<string[]>(categories);
	const [prevCategories, setPrevCategories] = useState<string[]>(categories);

	if (categories !== prevCategories) {
		setPrevCategories(categories);
		setLocalCategories(categories);
		setBackupCategories(categories);
	}

	// Sync local edit state with parent when prop changes
	if (isEditMode !== prevIsEditMode) {
		setPrevIsEditMode(isEditMode);
		setIsEditing(isEditMode);
		if (isEditMode) {
			setBackupCategories(localCategories);
		} else {
			setLocalCategories(categories);
			setBackupCategories(categories);
		}
	}

	const availableCategories = allCategories.filter((c) => !localCategories.includes(c.name));

	const filteredCategories = availableCategories.filter((c) =>
		c.name.toLowerCase().includes(inputValue.toLowerCase()),
	);

	const handleAddCategory = (catName: string) => {
		if (!localCategories.includes(catName)) {
			const nextCats = [...localCategories, catName];
			setLocalCategories(nextCats);
			onChangeCategories(nextCats);
		}
		setInputValue("");
		setOpen(false);
	};

	const handleRemoveCategory = (catName: string) => {
		const nextCats = localCategories.filter((c) => c !== catName);
		setLocalCategories(nextCats);
		onChangeCategories(nextCats);
	};

	const handleCancelCard = () => {
		setLocalCategories(backupCategories);
		onChangeCategories(backupCategories);
		setIsEditing(false);
	};

	const handleSaveCard = () => {
		onChangeCategories(localCategories);
		setBackupCategories(localCategories);
		setIsEditing(false);
	};

	return (
		<div className="bg-zinc-100/50 rounded-lg p-4 w-full text-zinc-950">
			<div className="flex items-center gap-2 text-blue-700 mb-2">
				<RiSparklingLine className="size-5 text-blue-600 shrink-0" />
				<h3 className="font-bold text-sm text-zinc-950">Suggested Categories</h3>
			</div>
			<p className="text-xs text-zinc-600 font-medium mb-4">
				The AI suggests the following tags for document indexing and chatbot routing.
			</p>

			<div className="flex flex-wrap gap-2 items-center mb-4">
				{localCategories.map((c) => (
					<div
						key={c}
						className="flex items-center gap-1.5 bg-white border border-zinc-300 px-3 py-1.5 rounded-lg text-sm font-semibold text-zinc-900 shadow-none"
					>
						<span>{c}</span>
						{isEditing && (
							<button
								type="button"
								onClick={() => handleRemoveCategory(c)}
								className="text-zinc-500 hover:text-red-600 hover:bg-red-50 p-0.5 rounded transition-colors cursor-pointer"
								title="Remove category"
							>
								<RiCloseLine className="size-4" />
							</button>
						)}
					</div>
				))}

				{isEditing && (
					<div className="relative flex-1 min-w-52 max-w-80">
						<Input
							ref={inputRef}
							value={inputValue}
							onChange={(e) => {
								setInputValue(e.target.value);
								setOpen(true);
							}}
							onFocus={() => setOpen(true)}
							onClick={() => setOpen(true)}
							onBlur={() => {
								setTimeout(() => setOpen(false), 200);
							}}
							placeholder="Type or select category..."
							className="border-zinc-300 bg-white focus-visible:border-zinc-400 focus-visible:ring-0 focus-visible:outline-none shadow-none h-9 text-sm font-medium text-zinc-900 rounded-lg placeholder:text-zinc-500"
						/>
						{open && (
							<div className="absolute top-full left-0 mt-1.5 w-full bg-white border border-zinc-300 rounded-lg shadow-none p-1.5 max-h-60 overflow-y-auto z-50">
								{filteredCategories.length > 0 ? (
									<div className="flex flex-col gap-0.5">
										{filteredCategories.map((cat) => (
											<div
												key={cat.id}
												role="button"
												tabIndex={0}
												onMouseDown={(e) => {
													e.preventDefault(); // prevent input blur
													handleAddCategory(cat.name);
												}}
												className="px-3 py-2 text-sm font-medium text-zinc-900 hover:bg-zinc-100 hover:text-zinc-950 cursor-pointer rounded-md transition-colors"
											>
												{cat.name}
											</div>
										))}
									</div>
								) : (
									<div className="px-3 py-2 text-xs font-medium text-zinc-500 text-center">
										No matching categories found in DB
									</div>
								)}
							</div>
						)}
					</div>
				)}
			</div>

			{!isEditing && isEditMode && (
				<Button
					variant="outline"
					className="w-fit mt-2 border-zinc-300 bg-white text-zinc-800 hover:bg-zinc-100 font-semibold rounded-lg px-4 h-9 text-sm transition-colors cursor-pointer shadow-none gap-2"
					onClick={() => setIsEditing(true)}
				>
					<RiEdit2Line className="size-4 text-zinc-700" />
					Edit Categories
				</Button>
			)}

			{isEditing && showSaveActions && (
				<div className="mt-6 flex flex-col gap-3">
					<p className="text-sm text-zinc-600 font-medium">Are these categories accurate?</p>
					<div className="flex items-center gap-2">
						<Button
							type="button"
							variant="outline"
							onClick={handleCancelCard}
							className="border-zinc-300 bg-white text-zinc-800 hover:bg-zinc-100 font-semibold rounded-lg px-4 h-10 text-sm transition-colors cursor-pointer shadow-none"
						>
							Cancel
						</Button>
						<Button
							type="button"
							className="bg-blue-600 hover:bg-blue-700 text-white font-semibold rounded-lg px-4 h-10 text-sm transition-colors cursor-pointer shadow-none"
							onClick={handleSaveCard}
						>
							Save Categories
						</Button>
					</div>
				</div>
			)}
		</div>
	);
}
