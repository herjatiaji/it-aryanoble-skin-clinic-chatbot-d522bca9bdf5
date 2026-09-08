import { Button } from "@/components/ui/button";
import { Field, FieldContent, FieldLabel, FieldTitle } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { RiDeleteBinLine, RiEyeLine, RiEyeOffLine, RiLoader4Line, RiEdit2Line, RiCheckLine, RiCloseLine } from "@remixicon/react";
import Image from "next/image";
import { useEffect, useState } from "react";
import { UserResponse } from "../api/types";
import { useDeleteUser, useUpdateStaffDetails } from "../hooks/use-users";

export function UserStaffProfileSheet({
	isOpen,
	onOpenChange,
	staff,
}: {
	isOpen: boolean;
	onOpenChange: (open: boolean) => void;
	staff: UserResponse | null;
}) {
	const [isEditing, setIsEditing] = useState(false);
	const [name, setName] = useState("");
	const [email, setEmail] = useState("");
	const [password, setPassword] = useState("");
	const [showPassword, setShowPassword] = useState(false);

	const deleteUser = useDeleteUser();
	const updateStaff = useUpdateStaffDetails();

	useEffect(() => {
		if (staff && isOpen) {
			setTimeout(() => {
				setName(staff.name || "");
				setEmail(staff.email || "");
				setPassword("");
				setIsEditing(false);
				setShowPassword(false);
			}, 0);
		}
	}, [staff, isOpen]);

	const handleDelete = () => {
		if (!staff) return;
		if (confirm(`Are you sure you want to delete ${staff.name}?`)) {
			deleteUser.mutate(staff.id, {
				onSuccess: () => onOpenChange(false),
			});
		}
	};

	const handleSave = () => {
		if (!staff) return;
		updateStaff.mutate(
			{
				userId: staff.id,
				data: {
					name,
					email,
					...(password ? { password } : {}),
				},
			},
			{
				onSuccess: () => setIsEditing(false),
			},
		);
	};

	return (
		<Sheet open={isOpen} onOpenChange={onOpenChange}>
			<SheetContent className="sm:max-w-100 p-0 flex flex-col h-full bg-white gap-0">
				<SheetHeader className="p-4 border-b flex flex-row items-center">
					<SheetTitle className="text-base font-medium">
						{isEditing ? "Edit Profile" : "User Profile"}
					</SheetTitle>
				</SheetHeader>

				{staff && (
					<>
						<div className="flex-1 overflow-y-auto pb-6">
							<div className="flex flex-col pb-4">
								{/* Profile Cover Image */}
								<div className="relative h-65 w-full bg-gray-100 overflow-hidden shrink-0">
									<Image src="/placeholder.svg" alt={staff.name} fill className="object-cover" />
								</div>

								{/* Details Section */}
								<div className="flex flex-col gap-6 px-6 py-4">
									<Field>
										<FieldLabel>
											<FieldTitle>Name</FieldTitle>
										</FieldLabel>
										<FieldContent>
											{isEditing ? (
												<div className="relative">
													<Input
														value={name}
														onChange={(e) => setName(e.target.value)}
														className="border-gray-200 bg-white focus-visible:ring-blue-500"
													/>
												</div>
											) : (
												<span className="text-sm text-gray-900">{staff.name}</span>
											)}
										</FieldContent>
									</Field>

									<Field>
										<FieldLabel>
											<FieldTitle>Role</FieldTitle>
										</FieldLabel>
										<FieldContent>
											<span className="text-sm text-gray-900">
												{staff.roles && staff.roles.length > 0 ? staff.roles[0].name : "Staff"}
											</span>
										</FieldContent>
									</Field>

									<Field>
										<FieldLabel>
											<FieldTitle>Email</FieldTitle>
										</FieldLabel>
										<FieldContent>
											{isEditing ? (
												<div className="relative">
													<Input
														value={email}
														onChange={(e) => setEmail(e.target.value)}
														type="email"
														className="border-gray-200 bg-white focus-visible:ring-blue-500"
														autoComplete="off"
													/>
												</div>
											) : (
												<span className="text-sm text-gray-900">{staff.email}</span>
											)}
										</FieldContent>
									</Field>

									<Field>
										<FieldLabel>
											<FieldTitle>{isEditing ? "New Password" : "Password"}</FieldTitle>
										</FieldLabel>
										<FieldContent>
											{isEditing ? (
												<div className="relative">
													<Input
														value={password}
														onChange={(e) => setPassword(e.target.value)}
														type={showPassword ? "text" : "password"}
														placeholder="Leave blank to keep"
														className="border-gray-200 bg-white focus-visible:ring-blue-500 pr-10"
														autoComplete="new-password"
													/>
													<Button
														variant="ghost"
														size="icon"
														className="absolute right-0 top-0 text-gray-500 hover:text-gray-700"
														onClick={() => setShowPassword(!showPassword)}
														type="button"
													>
														{showPassword ? (
															<RiEyeOffLine className="h-4 w-4" />
														) : (
															<RiEyeLine className="h-4 w-4" />
														)}
													</Button>
												</div>
											) : (
												<span className="text-sm text-gray-900">********</span>
											)}
										</FieldContent>
									</Field>

									{!isEditing && (
										<Field>
											<FieldLabel>
												<FieldTitle>Date & Time Created</FieldTitle>
											</FieldLabel>
											<FieldContent>
												<span className="text-sm text-gray-900">
													{new Date(staff.created_at).toLocaleString("en-US", {
														year: "numeric",
														month: "numeric",
														day: "numeric",
														hour: "numeric",
														minute: "numeric",
														hour12: true,
													})}
												</span>
											</FieldContent>
										</Field>
									)}
								</div>
							</div>
						</div>

						{isEditing ? (
							<div className="p-4 border-t border-gray-200 bg-white flex justify-end gap-3">
								<Button
									variant="outline"
									className="bg-white border-gray-200 text-gray-700 hover:bg-gray-50 hover:text-gray-900"
									onClick={() => {
										setIsEditing(false);
										if (staff) {
											setName(staff.name || "");
											setEmail(staff.email || "");
											setPassword("");
										}
									}}
								>
									<RiCloseLine className="mr-2 h-4 w-4 shrink-0" />
									Cancel
								</Button>
								<Button
									className="bg-blue-600 hover:bg-blue-700 text-white"
									onClick={handleSave}
									disabled={updateStaff.isPending}
								>
									{updateStaff.isPending ? (
										<RiLoader4Line className="mr-2 h-4 w-4 animate-spin shrink-0" />
									) : (
										<RiCheckLine className="mr-2 h-4 w-4 shrink-0" />
									)}
									{updateStaff.isPending ? "Saving..." : "Save Changes"}
								</Button>
							</div>
						) : (
							<div className="p-4 border-t border-gray-200 bg-white flex justify-end gap-3">
								<Button
									variant="outline"
									className="border-red-500 text-red-600 hover:bg-red-50 hover:text-red-700 disabled:opacity-50"
									onClick={handleDelete}
									disabled={deleteUser.isPending}
								>
									{deleteUser.isPending ? (
										<RiLoader4Line className="mr-2 h-4 w-4 animate-spin shrink-0" />
									) : (
										<RiDeleteBinLine className="mr-2 h-4 w-4 shrink-0" />
									)}
									{deleteUser.isPending ? "Deleting..." : "Delete User"}
								</Button>
								<Button
									className="bg-blue-600 text-white hover:bg-blue-700"
									onClick={() => setIsEditing(true)}
								>
									<RiEdit2Line className="mr-2 h-4 w-4 shrink-0" />
									Edit Profile
								</Button>
							</div>
						)}
					</>
				)}
			</SheetContent>
		</Sheet>
	);
}
