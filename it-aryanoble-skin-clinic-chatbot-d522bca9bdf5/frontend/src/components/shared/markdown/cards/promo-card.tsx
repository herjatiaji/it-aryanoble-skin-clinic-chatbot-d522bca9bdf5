import React from "react";
import { RiCalendarEventLine, RiCheckLine, RiCoupon3Line } from "@remixicon/react";
import type { PromoCardData } from "../types";

export function PromoCard({ data }: { data: PromoCardData }) {
	const { title, discount, originalPrice, promoPrice, period, terms, notes } = data;

	return (
		<div className="not-prose my-2.5 rounded-lg border-2 border-dashed border-amber-300 bg-linear-to-r from-amber-50/60 via-white to-amber-50/40 p-3.5 flex flex-col gap-2.5 shadow-none">
			{/* Top Bar: Icon + Title + Period Badge */}
			<div className="flex items-center justify-between gap-2 flex-wrap">
				<div className="flex items-center gap-2 min-w-0">
					<div className="size-6 sm:size-7 rounded-md bg-amber-500 text-white flex items-center justify-center shrink-0 shadow-xs">
						<RiCoupon3Line className="size-3.5 sm:size-4" />
					</div>
					<h4 className="text-sm sm:text-base font-semibold text-zinc-950 tracking-tight truncate">
						{title || "Program Promo Spesial"}
					</h4>
				</div>

				{period && (
					<div className="inline-flex items-center gap-1.5 text-xs font-medium text-amber-900 bg-amber-100/90 border border-amber-200/80 px-2.5 py-0.5 rounded-md shrink-0">
						<RiCalendarEventLine className="size-3 text-amber-700" />
						<span>{period}</span>
					</div>
				)}
			</div>

			{/* Pricing & Discount Banner */}
			{(discount || promoPrice || originalPrice) && (
				<div className="flex items-center gap-3 bg-white/90 p-2.5 rounded-md border border-amber-200/70">
					{discount && (
						<div className="px-2.5 py-1 rounded bg-red-600 text-white font-bold text-xs shadow-xs tracking-wide shrink-0">
							{discount}
						</div>
					)}
					<div className="flex items-baseline gap-2 flex-wrap">
						{promoPrice && (
							<span className="text-base sm:text-lg font-bold text-zinc-950">{promoPrice}</span>
						)}
						{originalPrice && (
							<span className="text-xs line-through text-zinc-400">{originalPrice}</span>
						)}
					</div>
				</div>
			)}

			{/* Terms & Conditions */}
			{terms && terms.length > 0 && (
				<div className="text-xs sm:text-sm text-zinc-700 bg-white/70 p-2.5 rounded-md border border-zinc-200/60">
					<span className="font-semibold text-zinc-900 block mb-1 text-xs">
						Syarat & Ketentuan:
					</span>
					<div className="space-y-0.5">
						{terms.map((term, idx) => (
							<div key={idx} className="flex items-start gap-1.5 leading-normal">
								<RiCheckLine className="size-3.5 text-emerald-600 shrink-0 mt-0.5" />
								<span>{term}</span>
							</div>
						))}
					</div>
				</div>
			)}

			{notes && (
				<p className="text-xs text-zinc-500 italic m-0">{notes}</p>
			)}
		</div>
	);
}
