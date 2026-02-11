"use client";

import { useCallback, useEffect, useState } from "react";
import { useSession, signOut } from "next-auth/react";
import { UserCircle, Crown, Check, Link2 } from "lucide-react";
import { usersAPI, type UserProfile, clearTokenCache } from "@/lib/api";
import { Button, Card, CardContent, Badge, Spinner } from "@/components/ui";

export default function ProfilePage() {
  const { data: session } = useSession();

  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);

  // Editable fields
  const [lichessUsername, setLichessUsername] = useState("");
  const [chesscomUsername, setChesscomUsername] = useState("");

  const loadProfile = useCallback(async () => {
    setLoading(true);
    try {
      const p = await usersAPI.me();
      setProfile(p);
      setLichessUsername(p.lichess_username ?? "");
      setChesscomUsername(p.chesscom_username ?? "");
    } catch {
      // API may not be connected
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (session) loadProfile();
  }, [session, loadProfile]);

  async function handleSave() {
    setSaving(true);
    setSaveMsg(null);
    try {
      const updated = await usersAPI.updateProfile({
        lichess_username: lichessUsername || undefined,
        chesscom_username: chesscomUsername || undefined,
      });
      setProfile(updated);
      setSaveMsg("Saved!");
      setTimeout(() => setSaveMsg(null), 2000);
    } catch (err) {
      setSaveMsg("Failed to save");
    } finally {
      setSaving(false);
    }
  }

  function handleSignOut() {
    clearTokenCache();
    signOut();
  }

  if (!session) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-gray-500">Sign in to view your profile.</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Spinner className="h-8 w-8 text-brand-500" />
      </div>
    );
  }

  const isPro = profile?.subscription_tier === "pro";

  return (
    <div className="max-w-3xl mx-auto px-6 py-8 space-y-8 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold">Profile</h1>
        <p className="text-gray-500 mt-1">Manage your account and settings.</p>
      </div>

      {/* Account info */}
      <Card>
        <CardContent>
          <div className="flex items-center gap-4">
            <div className="h-14 w-14 rounded-full bg-surface-2 flex items-center justify-center">
              <UserCircle className="h-8 w-8 text-gray-400" />
            </div>
            <div className="flex-1">
              <p className="font-semibold text-lg">
                {profile?.name || session.user?.name || session.user?.email}
              </p>
              <p className="text-sm text-gray-500">
                {profile?.email || session.user?.email}
              </p>
            </div>
            <Badge variant={isPro ? "success" : "default"}>
              {isPro ? "Pro" : "Free"}
            </Badge>
          </div>
        </CardContent>
      </Card>

      {/* Linked accounts */}
      <Card>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold flex items-center gap-2">
              <Link2 className="h-4 w-4 text-brand-400" />
              Linked Accounts
            </h3>
            {saveMsg && (
              <span
                className={`text-xs ${
                  saveMsg === "Saved!" ? "text-green-400" : "text-red-400"
                }`}
              >
                {saveMsg}
              </span>
            )}
          </div>

          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <span className="text-sm font-medium text-gray-400 w-24">
                Lichess
              </span>
              <input
                type="text"
                placeholder="Enter Lichess username"
                value={lichessUsername}
                onChange={(e) => setLichessUsername(e.target.value)}
                className="flex-1 px-3 py-1.5 rounded-lg bg-surface-2 border border-surface-3 text-sm text-white placeholder:text-gray-600 focus:outline-none focus:ring-2 focus:ring-brand-600/50"
              />
              {profile?.lichess_username && (
                <Check className="h-4 w-4 text-green-400 flex-shrink-0" />
              )}
            </div>
            <div className="flex items-center gap-3">
              <span className="text-sm font-medium text-gray-400 w-24">
                Chess.com
              </span>
              <input
                type="text"
                placeholder="Enter Chess.com username"
                value={chesscomUsername}
                onChange={(e) => setChesscomUsername(e.target.value)}
                className="flex-1 px-3 py-1.5 rounded-lg bg-surface-2 border border-surface-3 text-sm text-white placeholder:text-gray-600 focus:outline-none focus:ring-2 focus:ring-brand-600/50"
              />
              {profile?.chesscom_username && (
                <Check className="h-4 w-4 text-green-400 flex-shrink-0" />
              )}
            </div>
          </div>

          <Button
            onClick={handleSave}
            loading={saving}
            disabled={saving}
            size="sm"
          >
            Save Accounts
          </Button>
        </CardContent>
      </Card>

      {/* Subscription */}
      <Card>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold">Subscription</h3>
            <Badge variant={isPro ? "success" : "default"}>
              {isPro ? "Pro" : "Free"}
            </Badge>
          </div>

          {isPro ? (
            <div className="p-4 rounded-lg bg-green-900/20 border border-green-800/30">
              <div className="flex items-center gap-3 mb-2">
                <Crown className="h-5 w-5 text-green-400" />
                <h4 className="font-semibold text-green-300">
                  Pro Subscription Active
                </h4>
              </div>
              <p className="text-sm text-gray-400">
                You have unlimited AI Coach reviews, priority analysis, and all
                premium features.
              </p>
              {profile?.ai_coach_reviews_used !== undefined && (
                <p className="text-xs text-gray-500 mt-2">
                  AI Coach reviews used: {profile.ai_coach_reviews_used}
                </p>
              )}
            </div>
          ) : (
            <div className="p-4 rounded-lg bg-gradient-to-r from-brand-900/30 to-brand-800/20 border border-brand-700/30">
              <div className="flex items-center gap-3 mb-2">
                <Crown className="h-5 w-5 text-brand-400" />
                <h4 className="font-semibold text-brand-300">
                  Upgrade to Pro
                </h4>
              </div>
              <p className="text-sm text-gray-400 mb-3">
                Unlimited AI Coach reviews, priority analysis, and more.
              </p>
              <ul className="text-sm text-gray-400 space-y-1 mb-4">
                <li className="flex items-center gap-2">
                  <Check className="h-3 w-3 text-brand-400" />
                  Unlimited AI Coach game reviews
                </li>
                <li className="flex items-center gap-2">
                  <Check className="h-3 w-3 text-brand-400" />
                  Deep analysis (depth 20+)
                </li>
                <li className="flex items-center gap-2">
                  <Check className="h-3 w-3 text-brand-400" />
                  Spaced repetition puzzle trainer
                </li>
                <li className="flex items-center gap-2">
                  <Check className="h-3 w-3 text-brand-400" />
                  Opening repertoire tracking
                </li>
              </ul>
              <Button>Upgrade – €9/month</Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Sign out */}
      <div className="pt-4 border-t border-surface-3">
        <Button variant="ghost" onClick={handleSignOut}>
          Sign Out
        </Button>
      </div>
    </div>
  );
}
