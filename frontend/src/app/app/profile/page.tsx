"use client";

import { useQuery } from "@tanstack/react-query";

import { ProfileView } from "@/components/features/profile/ProfileView";
import { miniAppApi } from "@/lib/api/client";

export default function ProfilePage() {
  const profile = useQuery({ queryKey: ["profile"], queryFn: miniAppApi.me });
  return profile.data ? <ProfileView profile={profile.data} /> : null;
}
