import { KnowledgeSummary } from "@/components/shared/knowledge/knowledge-summary";
import { KnowledgeTable } from "@/components/shared/knowledge/knowledge-table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export default function KnowledgePage() {
	return (
		<div className="flex flex-col h-full gap-6 p-6">
			<KnowledgeSummary />

			<div className="mt-2">
				<Tabs defaultValue="product" className="w-full">
					<div className="flex justify-between items-end mb-0">
						<TabsList variant="line" className="m-0">
							<TabsTrigger
								value="product"
								className="font-medium text-sm text-gray-500 hover:text-blue-500 data-active:text-blue-500 data-active:after:bg-blue-500"
							>
								Product
							</TabsTrigger>
							<TabsTrigger
								value="treatment"
								className="font-medium text-sm text-gray-500 hover:text-blue-500 data-active:text-blue-500 data-active:after:bg-blue-500"
							>
								Treatment
							</TabsTrigger>
							<TabsTrigger
								value="promotional"
								className="font-medium text-sm text-gray-500 hover:text-blue-500 data-active:text-blue-500 data-active:after:bg-blue-500"
							>
								Promotional
							</TabsTrigger>
							<TabsTrigger
								value="other"
								className="font-medium text-sm text-gray-500 hover:text-blue-500 data-active:text-blue-500 data-active:after:bg-blue-500"
							>
								Other
							</TabsTrigger>
						</TabsList>
					</div>

					<TabsContent value="product" className="mt-0 outline-none">
						<KnowledgeTable type="PRODUCT" />
					</TabsContent>

					<TabsContent value="treatment" className="mt-0 outline-none">
						<KnowledgeTable type="TREATMENT" />
					</TabsContent>

					<TabsContent value="promotional" className="mt-0 outline-none">
						<KnowledgeTable type="PROMOTIONAL" />
					</TabsContent>

					<TabsContent value="other" className="mt-0 outline-none">
						<KnowledgeTable type="OTHER" />
					</TabsContent>
				</Tabs>
			</div>
		</div>
	);
}
