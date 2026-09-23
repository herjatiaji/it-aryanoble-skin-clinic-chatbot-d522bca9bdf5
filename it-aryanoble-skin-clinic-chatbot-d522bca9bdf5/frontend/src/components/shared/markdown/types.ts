export interface KeyValueItem {
	key: string;
	value: string;
}

export interface CardData {
	imageUrl?: string;
	rawImageUrl?: string;
	imageAlt?: string;
	items: KeyValueItem[];
}

export interface BeforeAfterImageItem {
	url: string;
	alt?: string;
	description?: string;
}

export interface BeforeAfterData {
	title?: string;
	beforeImage: BeforeAfterImageItem;
	afterImage: BeforeAfterImageItem;
	notes?: string[];
}

export interface ProcedureStep {
	stepNumber: number;
	title: string;
	description: string;
}

export interface SOPCardData {
	title?: string;
	preCare?: string[];
	steps: ProcedureStep[];
	aftercare?: string[];
}

export interface PromoCardData {
	title: string;
	discount?: string;
	originalPrice?: string;
	promoPrice?: string;
	period?: string;
	terms?: string[];
	notes?: string;
}

export interface DiagnosisCardData {
	primaryDiagnosis: string;
	severity?: string;
	patientCondition?: string;
	treatment?: string;
	product?: string;
	notes?: string[];
	contraindications?: string[];
}

export interface PricingTier {
	name: string;
	price: string;
	pricePerSession?: string;
	badge?: string;
	features: string[];
	isPopular?: boolean;
}

export interface TieredPricingCardData {
	title?: string;
	tiers: PricingTier[];
}

export interface ActionConfirmationData {
	actionType: "edit_preview" | "delete_preview";
	knowledgeId?: string;
	fieldName?: string;
	oldValue?: string;
	newValue?: string;
	summary?: string;
	confirmationPrompt?: string;
}

export interface Segment {
	type:
		| "markdown"
		| "product-card"
		| "treatment-card"
		| "regimen-card"
		| "dos-donts-card"
		| "before-after-card"
		| "sop-card"
		| "promo-card"
		| "diagnosis-card"
		| "tiered-pricing-card"
		| "action-confirmation-card";
	content: string;
	data?: CardData;
	beforeAfterData?: BeforeAfterData;
	sopData?: SOPCardData;
	promoData?: PromoCardData;
	diagnosisData?: DiagnosisCardData;
	pricingData?: TieredPricingCardData;
	actionData?: ActionConfirmationData;
}
