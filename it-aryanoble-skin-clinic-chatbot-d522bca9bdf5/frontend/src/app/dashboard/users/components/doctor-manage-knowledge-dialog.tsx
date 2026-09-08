"use client";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { RiCheckLine } from "@remixicon/react";
import { useState, useEffect } from "react";
import { UserResponse } from "../api/types";
import { useCategories } from "../../category/hooks/use-categories";
import { useUpdateDoctorCategories } from "../hooks/use-users";

export function DoctorManageKnowledgeDialog({
  isOpen,
  onOpenChange,
  doctor,
}: {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  doctor: UserResponse | null;
}) {
  const { data: categories = [] } = useCategories();
  const updateCategories = useUpdateDoctorCategories();
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  useEffect(() => {
    if (isOpen && doctor) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSelectedIds(doctor.categories?.map((c) => c.id) || []);
    }
  }, [isOpen, doctor]);

  const handleToggle = (id: string) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((i) => i !== id) : [...prev, id]
    );
  };

  const handleSave = () => {
    if (doctor) {
      updateCategories.mutate(
        { userId: doctor.id, categories: selectedIds },
        {
          onSuccess: () => {
            onOpenChange(false);
          },
        }
      );
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md p-0 flex flex-col gap-0 rounded-md overflow-hidden bg-white border-0">
        <DialogHeader className="p-4 border-b border-gray-100 flex flex-row items-center justify-between">
          <DialogTitle className="text-base font-medium text-gray-900">
            Manage Knowledge Base
          </DialogTitle>
        </DialogHeader>

        <div className="p-4 flex flex-col gap-4 max-h-[60vh] overflow-y-auto">
          {/* List of knowledge */}
          <div className="flex flex-col gap-3">
            {categories.length === 0 && (
              <div className="text-sm text-gray-500 text-center py-4">
                No knowledge categories available.
              </div>
            )}
            {categories.map((category) => {
              const isSelected = selectedIds.includes(category.id);
              return (
                <div
                  key={category.id}
                  className={`border rounded-md p-3 flex items-center justify-between cursor-pointer ${
                    isSelected
                      ? "border-blue-500 bg-blue-50"
                      : "border-gray-200"
                  }`}
                  onClick={() => handleToggle(category.id)}
                >
                  <div className="flex items-center gap-3 w-full">
                    <Checkbox
                      id={`knowledge-${category.id}`}
                      checked={isSelected}
                      onCheckedChange={() => handleToggle(category.id)}
                      className="data-[state=checked]:bg-blue-500 data-[state=checked]:border-blue-500"
                    />
                    <div className="flex flex-col">
                      <span className="text-sm font-medium text-gray-900">
                        {category.name}
                      </span>
                      {category.description && (
                        <span className="text-xs text-gray-500 line-clamp-1">
                          {category.description}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          <div className="bg-yellow-50 border border-yellow-200 rounded-md p-4 text-sm text-yellow-900">
            Choose one or more knowledge bases to assign to the doctor, ensuring the chatbot only responds with relevant information.
          </div>
        </div>

        <div className="p-4 border-t border-gray-100 flex justify-end">
          <Button
            variant="outline"
            className="bg-blue-500 text-white border-0 hover:bg-blue-600 px-6 rounded-md"
            onClick={handleSave}
            disabled={updateCategories.isPending}
          >
            <RiCheckLine className="mr-2 h-4 w-4" />
            Save Knowledge
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
