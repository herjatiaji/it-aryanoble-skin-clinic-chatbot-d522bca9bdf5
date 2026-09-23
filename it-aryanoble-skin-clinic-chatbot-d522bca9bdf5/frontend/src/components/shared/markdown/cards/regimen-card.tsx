import React from "react";
import type { CardData } from "../types";

export function RegimenCard({ data }: { data: CardData }) {
	const { items } = data;

	return (
		<div className="not-prose my-2 rounded-lg border border-zinc-200/80 bg-zinc-50/50 p-2.5 flex flex-col gap-2">
			<div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
				{items.map((item, idx) => {
					return (
						<div
							key={idx}
							className="p-2.5 rounded-md border border-zinc-200 bg-white text-xs sm:text-sm"
						>
							<div className="flex items-center gap-1.5 mb-1">
								<span className="text-xs font-medium text-zinc-800 bg-zinc-100 px-1.5 py-0.5 rounded border border-zinc-200">
									{item.key}
								</span>
							</div>
							<p className="text-xs sm:text-sm text-zinc-900 leading-normal m-0">{item.value}</p>
						</div>
					);
				})}
			</div>
		</div>
	);
}
