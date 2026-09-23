"use client";

import React from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { ActionConfirmationCard } from "./cards/action-card";
import { BeforeAfterCard } from "./cards/before-after-card";
import { DiagnosisCard } from "./cards/diagnosis-card";
import { DosAndDontsCard } from "./cards/dos-donts-card";
import { ProcedureStepperCard } from "./cards/stepper-card";
import { ProductCard } from "./cards/product-card";
import { PromoCard } from "./cards/promo-card";
import { RegimenCard } from "./cards/regimen-card";
import { TieredPricingCard } from "./cards/pricing-card";
import { TreatmentCard } from "./cards/treatment-card";
import { defaultMarkdownComponents, createEditableMarkdownComponents } from "./elements";
import { parseMarkdownSegments } from "./parser";
import { stripInternalMetadata } from "./utils";

export interface MarkdownContentProps {
	content: string;
	components?: Components;
	onDeleteImage?: (src: string, alt: string) => void;
}

export function MarkdownContent({ content, components, onDeleteImage }: MarkdownContentProps) {
	const sanitizedContent = stripInternalMetadata(content);
	const baseComponents = onDeleteImage
		? { ...createEditableMarkdownComponents(onDeleteImage), ...components }
		: { ...defaultMarkdownComponents, ...components };
	const mergedComponents = baseComponents;
	const segments = parseMarkdownSegments(sanitizedContent);

	if (segments.length === 1 && segments[0].type === "markdown") {
		return (
			<ReactMarkdown remarkPlugins={[remarkGfm]} components={mergedComponents}>
				{sanitizedContent}
			</ReactMarkdown>
		);
	}

	return (
		<div className="flex flex-col gap-1">
			{segments.map((seg, idx) => {
				if (seg.type === "product-card" && seg.data) {
					return <ProductCard key={idx} data={seg.data} onDeleteImage={onDeleteImage} />;
				}
				if (seg.type === "treatment-card" && seg.data) {
					return <TreatmentCard key={idx} data={seg.data} onDeleteImage={onDeleteImage} />;
				}
				if (seg.type === "regimen-card" && seg.data) {
					return <RegimenCard key={idx} data={seg.data} />;
				}
				if (seg.type === "dos-donts-card" && seg.data) {
					return <DosAndDontsCard key={idx} data={seg.data} />;
				}
				if (seg.type === "before-after-card" && seg.beforeAfterData) {
					return <BeforeAfterCard key={idx} data={seg.beforeAfterData} />;
				}
				if (seg.type === "sop-card" && seg.sopData) {
					return <ProcedureStepperCard key={idx} data={seg.sopData} />;
				}
				if (seg.type === "promo-card" && seg.promoData) {
					return <PromoCard key={idx} data={seg.promoData} />;
				}
				if (seg.type === "diagnosis-card" && seg.diagnosisData) {
					return <DiagnosisCard key={idx} data={seg.diagnosisData} />;
				}
				if (seg.type === "tiered-pricing-card" && seg.pricingData) {
					return <TieredPricingCard key={idx} data={seg.pricingData} />;
				}
				if (seg.type === "action-confirmation-card" && seg.actionData) {
					return <ActionConfirmationCard key={idx} data={seg.actionData} />;
				}
				return (
					<ReactMarkdown key={idx} remarkPlugins={[remarkGfm]} components={mergedComponents}>
						{seg.content}
					</ReactMarkdown>
				);
			})}
		</div>
	);
}
