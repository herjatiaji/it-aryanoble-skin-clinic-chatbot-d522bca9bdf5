import React from "react";
import type { CardData } from "../types";

export function DosAndDontsCard({ data }: { data: CardData }) {
	const { items } = data;

	const dosItems = items.filter((item) => /do|anjuran|boleh|disarankan/i.test(item.key));
	const dontsItems = items.filter((item) => /don't|larangan|dilarang|tidak boleh/i.test(item.key));

	return (
		<div className="not-prose my-2 grid grid-cols-1 sm:grid-cols-2 gap-2">
			{dosItems.length > 0 && (
				<div className="p-2.5 rounded-md border-l-2 border-emerald-600 bg-emerald-50/30 text-xs sm:text-sm">
					<span className="block text-xs font-semibold text-emerald-950 mb-1">
						Anjuran (Do&apos;s)
					</span>
					<div className="space-y-1">
						{dosItems.map((item, idx) => (
							<div key={idx} className="text-zinc-800 leading-normal">
								• {item.value}
							</div>
						))}
					</div>
				</div>
			)}
			{dontsItems.length > 0 && (
				<div className="p-2.5 rounded-md border-l-2 border-red-600 bg-red-50/30 text-xs sm:text-sm">
					<span className="block text-xs font-semibold text-red-950 mb-1">
						Larangan (Don&apos;ts)
					</span>
					<div className="space-y-1">
						{dontsItems.map((item, idx) => (
							<div key={idx} className="text-zinc-800 leading-normal">
								• {item.value}
							</div>
						))}
					</div>
				</div>
			)}
		</div>
	);
}
