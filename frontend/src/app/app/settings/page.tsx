"use client";

import { useQuery } from "@tanstack/react-query";

import { AgentSettingsView } from "@/components/features/settings/AgentSettingsView";
import { miniAppApi } from "@/lib/api/client";

export default function SettingsPage() {
  const profile = useQuery({ queryKey: ["profile"], queryFn: miniAppApi.me });
  return profile.data ? <AgentSettingsView profile={profile.data} /> : null;
}
