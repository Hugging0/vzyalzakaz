"use client";

import { useQuery } from "@tanstack/react-query";

import { TodayView } from "@/components/features/today/TodayView";
import { miniAppApi } from "@/lib/api/client";

export default function TodayPage() {
  const profile = useQuery({ queryKey: ["profile"], queryFn: miniAppApi.me });
  return profile.data ? <TodayView profile={profile.data} /> : null;
}
