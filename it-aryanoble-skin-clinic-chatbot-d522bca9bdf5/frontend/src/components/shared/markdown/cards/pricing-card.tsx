import React from "react";
import { RiCheckLine, RiPriceTag3Line } from "@remixicon/react";
import type { TieredPricingCardData } from "../types";

export function TieredPricingCard({ data }: { data: TieredPricingCardData }) {
	const { title, tiers } = data;

	return (
		<div className="not-prose my-2 flex flex-col gap-1.5">
			{title && (
				<div className="flex items-center gap-1.5 text-xs font-semibold text-zinc-900">
					<RiPriceTag3Line className="size-3.5 text-blue-600" />
					<span>{title}</span>
				</div>
			)}

			<div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2">
				{tiers.map((tier, idx) => {
					const isPopular = tier.isPopular || /paket|rekomendasi|best|hemat/i.test(tier.name);
					return (
						<div
							key={idx}
							className={`rounded-lg border p-2.5 flex flex-col justify-between relative transition-colors ${
								isPopular
									? "border-blue-300 bg-blue-50/20"
									: "border-zinc-200/80 bg-white"
							}`}
						>
							<div>
								<div className="flex items-center justify-between gap-1 mb-1">
									<span className="text-xs font-semibold text-zinc-900 tracking-tight">
										{tier.name}
									</span>
									{tier.badge ? (
										<span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-blue-600 text-white">
											{tier.badge}
										</span>
									) : isPopular ? (
										<span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-200/80">
											Best Value
										</span>
									) : null}
								</div>

								<div className="mb-1.5">
									<div className="text-sm font-semibold text-zinc-950">{tier.price}</div>
									{tier.pricePerSession && (
										<div className="text-[11px] text-zinc-500">{tier.pricePerSession}</div>
									)}
								</div>

								{tier.features && tier.features.length > 0 && (
									<div className="space-y-0.5 text-xs text-zinc-600 border-t border-zinc-100 pt-1.5">
										{tier.features.map((feat, fIdx) => (
											<div key={fIdx} className="flex items-start gap-1 leading-normal">
												<RiCheckLine className="size-3 text-emerald-600 shrink-0 mt-0.5" />
												<span className="text-[11.5px]">{feat}</span>
											</div>
										))}
									</div>
								)}
							</div>
						</div>
					);
				})}
			</div>
		</div>
	);
}
