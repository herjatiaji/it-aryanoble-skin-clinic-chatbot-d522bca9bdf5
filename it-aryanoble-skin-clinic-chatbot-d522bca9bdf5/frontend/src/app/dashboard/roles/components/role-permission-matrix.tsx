"use client";

import { Checkbox } from "@/components/ui/checkbox";
import { MODULES_CONFIG, ModuleConfig } from "./role-dialog-config";

interface RolePermissionMatrixProps {
	selectedUiKeys: string[];
	onToggleGlobalSelectAll: () => void;
	onToggleModule: (module: ModuleConfig) => void;
	onToggleAction: (
		module: ModuleConfig,
		actionId: "create" | "read" | "update" | "delete",
		actionKey: string,
	) => void;
}

export function RolePermissionMatrix({
	selectedUiKeys,
	onToggleGlobalSelectAll,
	onToggleModule,
	onToggleAction,
}: RolePermissionMatrixProps) {
	const totalModules = MODULES_CONFIG.length;
	const selectedModulesCount = MODULES_CONFIG.filter((m) =>
		m.actions.some((a) => selectedUiKeys.includes(a.key)),
	).length;
	const isAllSelected = selectedModulesCount === totalModules;

	return (
		<div className="space-y-3">
			<div className="flex items-center justify-between">
				<span className="text-sm font-normal text-gray-900">Role Permission</span>
				<label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer select-none">
					<Checkbox checked={isAllSelected} onCheckedChange={onToggleGlobalSelectAll} />
					<span className="text-sm text-gray-700">
						Select All ({selectedModulesCount} out of {totalModules})
					</span>
				</label>
			</div>

			{/* Module Rows List */}
			<div className="divide-y divide-gray-100 border border-gray-100 rounded-lg overflow-hidden bg-white">
				{MODULES_CONFIG.map((module) => {
					const moduleKeys = module.actions.map((a) => a.key);
					const isModuleActive = moduleKeys.some((k) => selectedUiKeys.includes(k));

					return (
						<div
							key={module.id}
							className="flex flex-col sm:flex-row sm:items-center justify-between p-3.5 gap-3 hover:bg-gray-50/50 transition-colors"
						>
							{/* Module Title Checkbox */}
							<label className="flex items-center gap-2.5 cursor-pointer min-w-44 select-none">
								<Checkbox checked={isModuleActive} onCheckedChange={() => onToggleModule(module)} />
								<span className="text-sm font-normal text-gray-800">{module.name}</span>
							</label>

							{/* Action Checkboxes (Create, Read, Update, Delete) */}
							<div className="flex items-center flex-wrap gap-4 sm:gap-6">
								{module.actions.map((action) => {
									const isChecked = selectedUiKeys.includes(action.key);
									return (
										<label
											key={`${module.id}-${action.id}`}
											className="flex items-center gap-2 cursor-pointer text-sm text-gray-600 hover:text-gray-900 select-none"
										>
											<Checkbox
												checked={isChecked}
												onCheckedChange={() => onToggleAction(module, action.id, action.key)}
											/>
											<span className="text-sm text-gray-700">{action.label}</span>
										</label>
									);
								})}
							</div>
						</div>
					);
				})}
			</div>
		</div>
	);
}
