import { useState, useEffect } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Switch } from '@/components/ui/switch';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useToast } from '@/components/ui/toast';
import { generateId } from '@/lib/utils';
import { parseToml, stringifyToml } from '@/lib/toml';
import { ContextProfile, Snippet } from '@/types/chat';
import { ProvidersTab } from '@/components/ProvidersTab';
import { ToolsTab } from '@/components/ToolsTab';
import {
  AVAILABLE_MODELS,
  getModelsWithStatus,
  downloadModel,
  removeModelFromDownloaded,
  clearAllModels,
  type ModelInfo,
  type DownloadProgress,
} from '@/lib/ml/model-manager';
import {
  Download,
  Trash2,
  Check,
  Loader2,
  AlertCircle,
  Plus,
  Copy,
  Edit2,
  Book,
} from 'lucide-react';
import { useJunasContext } from '@/lib/context/JunasContext';
import { ASCII_LOGOS } from '@/lib/ascii-logos';
import { toActionableToastDescription } from '@/lib/tauri-error';
import { WINDOW_EVENTS, isOpenConfigDialogEvent, type ConfigDialogTab } from '@/lib/events';
import { z } from 'zod';

interface ConfigDialogProps {
  isOpen: boolean;
  onClose: () => void;
}

const TomlSettingsSchema = z
  .object({
    temperature: z.number().min(0).max(2).optional(),
    maxTokens: z.number().int().min(1).max(128000).optional(),
    topP: z.number().min(0).max(1).optional(),
    topK: z.number().int().min(1).max(1000).optional(),
    frequencyPenalty: z.number().min(-2).max(2).optional(),
    presencePenalty: z.number().min(-2).max(2).optional(),
    systemPrompt: z.string().optional(),
    autoSave: z.boolean().optional(),
    darkMode: z.boolean().optional(),
    agentMode: z.boolean().optional(),
    focusMode: z.boolean().optional(),
    theme: z
      .enum([
        'vanilla',
        'gruvbox',
        'everforest',
        'tokyo-night',
        'catppuccin',
        'solarized',
        'rose-pine',
        'kanagawa',
        'nord',
        'cyberpunk',
      ])
      .optional(),
    asciiLogo: z.string().optional(),
    profile: z
      .object({
        userRole: z.string().optional(),
        userPurpose: z.string().optional(),
      })
      .optional(),
  })
  .passthrough();

type Tab = ConfigDialogTab;

export function ConfigDialog({ isOpen, onClose }: ConfigDialogProps) {
  const { settings, updateSettings } = useJunasContext();
  const [activeTab, setActiveTab] = useState<Tab>('profile');

  // Listen for custom event to open Providers tab
  // Keeping this for now as it might be triggered from other non-React parts or simple commands
  useEffect(() => {
    const handler = (event: Event) => {
      if (isOpenConfigDialogEvent(event)) {
        setActiveTab(event.detail.tab);
      }
    };
    window.addEventListener(WINDOW_EVENTS.openConfigDialog, handler);
    return () => window.removeEventListener(WINDOW_EVENTS.openConfigDialog, handler);
  }, []);

  // Profile state
  const [userRole, setUserRole] = useState('');
  const [userPurpose, setUserPurpose] = useState('');
  const [profileSystemPrompt, setProfileSystemPrompt] = useState('');
  const [profiles, setProfiles] = useState<ContextProfile[]>([]);
  const [activeProfileId, setActiveProfileId] = useState<string>('');
  const [profileName, setProfileName] = useState('');

  // Snippet state
  const [snippets, setSnippets] = useState<Snippet[]>([]);
  const [editingSnippetId, setEditingSnippetId] = useState<string | null>(null);
  const [snippetTitle, setSnippetTitle] = useState('');
  const [snippetContent, setSnippetContent] = useState('');

  const [tomlContent, setTomlContent] = useState('');

  // Generation state
  const [temperature, setTemperature] = useState(0.7);
  const [maxTokens, setMaxTokens] = useState(4000);
  const [topP, setTopP] = useState(0.95);
  const [topK, setTopK] = useState(40);
  const [frequencyPenalty, setFrequencyPenalty] = useState(0.0);
  const [presencePenalty, setPresencePenalty] = useState(0.0);
  const [systemPrompt, setSystemPrompt] = useState('');

  // Models state
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [downloadingModels, setDownloadingModels] = useState<Record<string, DownloadProgress>>({});
  const [showDeleteModelsConfirm, setShowDeleteModelsConfirm] = useState(false);
  const [showClearDataConfirm, setShowClearDataConfirm] = useState(false);
  const { addToast } = useToast();

  // Sync state with settings from context when dialog opens
  useEffect(() => {
    if (isOpen) {
      setUserRole(settings.userRole || '');
      setUserPurpose(settings.userPurpose || '');
      setProfiles(settings.profiles || []);
      setSnippets(settings.snippets || []);

      const currentProfileId = settings.activeProfileId || '';
      setActiveProfileId(currentProfileId);

      if (currentProfileId && settings.profiles) {
        const p = settings.profiles.find((p) => p.id === currentProfileId);
        if (p) {
          setProfileName(p.name);
          setUserRole(p.userRole);
          setUserPurpose(p.userPurpose);
        }
      }

      setTemperature(settings.temperature ?? 0.7);
      setMaxTokens(settings.maxTokens ?? 4000);
      setTopP(settings.topP ?? 0.95);
      setTopK(settings.topK ?? 40);
      setFrequencyPenalty(settings.frequencyPenalty ?? 0.0);
      setPresencePenalty(settings.presencePenalty ?? 0.0);
      setSystemPrompt(settings.systemPrompt || '');

      // Load models status
      getModelsWithStatus()
        .then(setModels)
        .catch(() => setModels([]));
    }
  }, [isOpen, settings]);

  useEffect(() => {
    if (activeTab === 'developer' && isOpen) {
      const config = {
        // ... (use settings directly)
        temperature: settings.temperature,
        maxTokens: settings.maxTokens,
        topP: settings.topP,
        topK: settings.topK,
        frequencyPenalty: settings.frequencyPenalty,
        presencePenalty: settings.presencePenalty,
        systemPrompt: settings.systemPrompt,
        autoSave: settings.autoSave,
        darkMode: settings.darkMode,
        agentMode: settings.agentMode,
        focusMode: settings.focusMode,
        theme: settings.theme,
        asciiLogo: settings.asciiLogo,
        profile: {
          userRole: settings.userRole,
          userPurpose: settings.userPurpose,
        },
      };
      setTomlContent(stringifyToml(config));
    }
  }, [activeTab, isOpen, settings]);

  const handleProfileChange = (id: string) => {
    if (id === 'global') {
      setUserRole(settings.userRole || '');
      setUserPurpose(settings.userPurpose || '');
      setProfileSystemPrompt('');
      setProfileName('');
      setActiveProfileId('');
    } else {
      const p = profiles.find((p) => p.id === id);
      if (p) {
        setUserRole(p.userRole);
        setUserPurpose(p.userPurpose);
        setProfileSystemPrompt(p.systemPrompt || '');
        setProfileName(p.name);
        setActiveProfileId(id);
      }
    }
  };

  const handleCreateProfile = () => {
    const newProfile: ContextProfile = {
      id: generateId(),
      name: 'New Profile',
      userRole: userRole,
      userPurpose: userPurpose,
      systemPrompt: profileSystemPrompt,
    };
    setProfiles([...profiles, newProfile]);
    setActiveProfileId(newProfile.id);
    setProfileName(newProfile.name);
  };

  const handleDeleteProfile = () => {
    if (!activeProfileId) return;
    const newProfiles = profiles.filter((p) => p.id !== activeProfileId);
    setProfiles(newProfiles);
    handleProfileChange('global'); // Switch back to global
  };

  const handleSaveProfile = () => {
    let updatedProfiles = [...profiles];

    // If active profile, update it in the array
    if (activeProfileId) {
      updatedProfiles = updatedProfiles.map((p) =>
        p.id === activeProfileId
          ? { ...p, name: profileName, userRole, userPurpose, systemPrompt: profileSystemPrompt }
          : p
      );
      setProfiles(updatedProfiles);
    }

    updateSettings({
      ...settings,
      userRole: activeProfileId ? settings.userRole : userRole, // Only update global if global selected
      userPurpose: activeProfileId ? settings.userPurpose : userPurpose,
      profiles: updatedProfiles,
      activeProfileId: activeProfileId || undefined,
    });

    onClose();

    addToast({
      title: 'Profile Saved',
      description: activeProfileId
        ? `Profile "${profileName}" updated.`
        : 'Global context updated.',
      duration: 2000,
    });
  };

  const handleSaveGeneration = () => {
    updateSettings({
      ...settings,
      temperature,
      maxTokens,
      topP,
      topK,
      frequencyPenalty,
      presencePenalty,
      systemPrompt,
    });

    addToast({
      title: 'Settings Saved',
      description: 'Generation parameters have been updated.',
      duration: 2000,
    });
  };

  const handleCreateSnippet = () => {
    setEditingSnippetId('new');
    setSnippetTitle('');
    setSnippetContent('');
  };

  const handleEditSnippet = (snippet: Snippet) => {
    setEditingSnippetId(snippet.id);
    setSnippetTitle(snippet.title);
    setSnippetContent(snippet.content);
  };

  const handleSaveSnippet = () => {
    let newSnippets = [...snippets];

    if (editingSnippetId === 'new') {
      const newSnippet: Snippet = {
        id: generateId(),
        title: snippetTitle || 'Untitled Snippet',
        content: snippetContent,
        createdAt: Date.now(),
      };
      newSnippets.push(newSnippet);
    } else {
      newSnippets = newSnippets.map((s) =>
        s.id === editingSnippetId ? { ...s, title: snippetTitle, content: snippetContent } : s
      );
    }

    setSnippets(newSnippets);
    updateSettings({ ...settings, snippets: newSnippets });
    setEditingSnippetId(null);

    addToast({
      title: 'Snippet Saved',
      description: 'Your snippet has been saved.',
      duration: 2000,
    });
  };

  const handleDeleteSnippet = (id: string) => {
    const newSnippets = snippets.filter((s) => s.id !== id);
    setSnippets(newSnippets);
    updateSettings({ ...settings, snippets: newSnippets });
    if (editingSnippetId === id) setEditingSnippetId(null);
  };

  const handleSaveToml = () => {
    try {
      const parsed = parseToml(tomlContent);
      const validation = TomlSettingsSchema.safeParse(parsed);
      if (!validation.success) {
        throw new Error(validation.error.issues[0]?.message || 'Invalid TOML configuration.');
      }
      const validatedConfig = validation.data;

      // Use 'any' to allow property manipulation before saving
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const mergedConfig: any = { ...settings, ...validatedConfig };

      if (validatedConfig.profile) {
        mergedConfig.userRole = validatedConfig.profile.userRole || mergedConfig.userRole;
        mergedConfig.userPurpose = validatedConfig.profile.userPurpose || mergedConfig.userPurpose;
        delete mergedConfig.profile;
      }

      updateSettings(mergedConfig);

      // Update local state to reflect changes
      setTemperature(mergedConfig.temperature ?? temperature);
      setMaxTokens(mergedConfig.maxTokens ?? maxTokens);
      setTopP(mergedConfig.topP ?? topP);

      addToast({
        title: 'Configuration Applied',
        description: 'Settings updated from TOML.',
        duration: 2000,
      });
      onClose();
    } catch (e: any) {
      addToast({
        type: 'error',
        title: 'Parse Error',
        description: e?.message || 'Invalid TOML format.',
        duration: 3000,
      });
    }
  };

  const handleDownloadModel = async (modelId: string) => {
    try {
      setDownloadingModels((prev) => ({
        ...prev,
        [modelId]: {
          modelId,
          progress: 0,
          loaded: 0,
          total: 0,
          status: 'downloading',
        },
      }));

      await downloadModel(modelId, (progress) => {
        setDownloadingModels((prev) => ({
          ...prev,
          [modelId]: progress,
        }));
      });

      // Refresh models list
      setModels(await getModelsWithStatus());

      // Get model name for toast
      const modelInfo = AVAILABLE_MODELS.find((m) => m.id === modelId);
      addToast({
        type: 'success',
        title: 'Model Ready',
        description: `${modelInfo?.name || modelId} has been downloaded and is ready to use.`,
        duration: 4000,
      });

      // Clear from downloading state after a delay
      setTimeout(() => {
        setDownloadingModels((prev) => {
          const updated = { ...prev };
          delete updated[modelId];
          return updated;
        });
      }, 2000);
    } catch (error: any) {
      setDownloadingModels((prev) => ({
        ...prev,
        [modelId]: {
          modelId,
          progress: 0,
          loaded: 0,
          total: 0,
          status: 'error',
          error: error.message,
        },
      }));

      const modelInfo = AVAILABLE_MODELS.find((m) => m.id === modelId);
      addToast({
        type: 'error',
        title: 'Download Failed',
        description: toActionableToastDescription(
          error,
          `Failed to download ${modelInfo?.name || modelId}`
        ),
        duration: 5000,
      });
    }
  };

  const handleRemoveModel = async (modelId: string) => {
    await removeModelFromDownloaded(modelId);
    setModels(await getModelsWithStatus());
  };

  const handleDeleteAllModels = async () => {
    setShowDeleteModelsConfirm(false);
    try {
      await clearAllModels();
      setModels(await getModelsWithStatus());
      addToast({
        type: 'success',
        title: 'Models Deleted',
        description: 'All local models have been removed from your device.',
        duration: 3000,
      });
    } catch (error: any) {
      addToast({
        type: 'error',
        title: 'Error',
        description: toActionableToastDescription(error, 'Failed to delete models'),
        duration: 3000,
      });
    }
  };

  const handleClearSiteData = () => {
    setShowClearDataConfirm(false);
    try {
      localStorage.clear();
      sessionStorage.clear();

      // Also try to clear model cache
      clearAllModels().then(() => {
        window.location.reload();
      });
    } catch (error) {
      window.location.reload();
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-4xl font-mono h-[80vh] flex flex-row p-0 overflow-hidden gap-0">
        {/* Sidebar */}
        <div className="w-56 bg-muted/30 border-r flex flex-col shrink-0">
          <DialogHeader className="p-4 border-b bg-background/50">
            <DialogTitle className="text-sm">[ Configuration ]</DialogTitle>
          </DialogHeader>
          <div className="flex flex-col py-2">
            {[
              { id: 'profile', label: 'Profile' },
              { id: 'generation', label: 'Generation' },
              { id: 'localModels', label: 'Local Models' },
              { id: 'providers', label: 'Providers' },
              { id: 'tools', label: 'Tools' },
              { id: 'snippets', label: 'Snippets' },
              { id: 'interface', label: 'Interface' },
              { id: 'developer', label: 'Developer' },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as Tab)}
                className={`px-4 py-2.5 text-xs text-left transition-colors font-medium border-l-2 ${
                  activeTab === tab.id
                    ? 'border-primary bg-primary/5 text-primary'
                    : 'border-transparent text-muted-foreground hover:bg-muted hover:text-foreground'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <div className="mt-auto p-4 border-t text-[10px] text-muted-foreground opacity-50">
            v1.0.0
          </div>
        </div>

        {/* Content Area */}
        <div className="flex-1 flex flex-col min-w-0 bg-background">
          {/* Tab Content */}
          {/* Tab Content */}
          <div className="flex-1 overflow-y-auto p-6 no-scrollbar">
            {activeTab === 'profile' && (
              <div className="space-y-4">
                <div className="flex items-center gap-2 mb-4">
                  <div className="flex-1">
                    <Label className="text-xs font-mono mb-1.5 block">Active Profile</Label>
                    <div className="relative">
                      <select
                        value={activeProfileId || 'global'}
                        onChange={(e) => handleProfileChange(e.target.value)}
                        className="w-full text-xs font-mono bg-background border border-input rounded-md px-3 py-2 focus:outline-none focus:ring-1 focus:ring-primary appearance-none"
                      >
                        <option value="global">Global (Default)</option>
                        {profiles.map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.name}
                          </option>
                        ))}
                      </select>
                      <div className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none text-muted-foreground text-[10px]">
                        ▼
                      </div>
                    </div>
                  </div>
                  <div className="flex items-end gap-1">
                    <button
                      onClick={handleCreateProfile}
                      className="p-2 border border-input rounded-md hover:bg-muted transition-colors"
                      title="Create New Profile"
                    >
                      <Plus className="h-4 w-4" />
                    </button>
                    {activeProfileId && (
                      <button
                        onClick={handleDeleteProfile}
                        className="p-2 border border-red-200 text-red-500 rounded-md hover:bg-red-50 transition-colors"
                        title="Delete Profile"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    )}
                  </div>
                </div>

                {activeProfileId && (
                  <div className="space-y-2 p-3 bg-muted/20 rounded-md border border-muted-foreground/10">
                    <Label htmlFor="profileName" className="text-xs font-mono">
                      Profile Name
                    </Label>
                    <Input
                      id="profileName"
                      value={profileName}
                      onChange={(e) => setProfileName(e.target.value)}
                      className="text-xs font-mono bg-background"
                    />
                  </div>
                )}

                <p className="text-xs text-muted-foreground">
                  Set your role and purpose to help Junas provide more relevant assistance.
                </p>

                <div className="space-y-2">
                  <Label htmlFor="userRole" className="text-xs font-mono">
                    &gt; Your Role
                  </Label>
                  <Input
                    id="userRole"
                    placeholder="e.g., lawyer, law student, legal researcher"
                    value={userRole}
                    onChange={(e) => setUserRole(e.target.value)}
                    className="text-xs font-mono"
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="userPurpose" className="text-xs font-mono">
                    &gt; Your Purpose
                  </Label>
                  <Input
                    id="userPurpose"
                    placeholder="e.g., contract analysis, case law research"
                    value={userPurpose}
                    onChange={(e) => setUserPurpose(e.target.value)}
                    className="text-xs font-mono"
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="profileSystemPrompt" className="text-xs font-mono">
                    &gt; Custom System Prompt (Optional)
                  </Label>
                  <textarea
                    id="profileSystemPrompt"
                    value={profileSystemPrompt}
                    onChange={(e) => setProfileSystemPrompt(e.target.value)}
                    className="w-full h-24 p-3 text-xs font-mono bg-background border rounded-md resize-none focus:outline-none focus:ring-1 focus:ring-primary"
                    placeholder="Override the default system prompt for this profile..."
                  />
                </div>

                <div className="space-y-2">
                  <Label className="text-xs font-mono">&gt; Context Preview</Label>
                  <p className="text-xs text-muted-foreground pl-1">
                    {userRole || '[Your Role]'} using Junas for {userPurpose || '[Your Purpose]'}
                  </p>
                </div>

                <div className="flex justify-end gap-2 pt-4">
                  <button
                    onClick={handleSaveProfile}
                    className="px-3 py-2 text-xs bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
                  >
                    [ Save ]
                  </button>
                </div>
              </div>
            )}

            {activeTab === 'generation' && (
              <div className="space-y-4 px-1">
                <p className="text-xs text-muted-foreground">
                  Fine-tune how the AI generates responses.
                </p>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="temp" className="text-xs font-mono">
                      Temperature
                    </Label>
                    <Input
                      id="temp"
                      type="number"
                      min="0"
                      max="2"
                      step="0.1"
                      value={temperature}
                      onChange={(e) => setTemperature(parseFloat(e.target.value))}
                      className="text-xs font-mono"
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="topP" className="text-xs font-mono">
                      Top P
                    </Label>
                    <Input
                      id="topP"
                      type="number"
                      min="0"
                      max="1"
                      step="0.01"
                      value={topP}
                      onChange={(e) => setTopP(parseFloat(e.target.value))}
                      className="text-xs font-mono"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="freqPen" className="text-xs font-mono">
                      Frequency Penalty
                    </Label>
                    <Input
                      id="freqPen"
                      type="number"
                      min="-2"
                      max="2"
                      step="0.1"
                      value={frequencyPenalty}
                      onChange={(e) => setFrequencyPenalty(parseFloat(e.target.value))}
                      className="text-xs font-mono"
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="presPen" className="text-xs font-mono">
                      Presence Penalty
                    </Label>
                    <Input
                      id="presPen"
                      type="number"
                      min="-2"
                      max="2"
                      step="0.1"
                      value={presencePenalty}
                      onChange={(e) => setPresencePenalty(parseFloat(e.target.value))}
                      className="text-xs font-mono"
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="maxTokens" className="text-xs font-mono">
                    Max Tokens
                  </Label>
                  <Input
                    id="maxTokens"
                    type="number"
                    value={maxTokens}
                    onChange={(e) => setMaxTokens(parseInt(e.target.value))}
                    className="text-xs font-mono"
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="systemPrompt" className="text-xs font-mono">
                    System Prompt
                  </Label>
                  <textarea
                    id="systemPrompt"
                    value={systemPrompt}
                    onChange={(e) => setSystemPrompt(e.target.value)}
                    className="w-full h-32 p-3 text-xs font-mono bg-background border rounded-md resize-none focus:outline-none focus:ring-1 focus:ring-primary"
                    placeholder="Enter custom system instructions..."
                  />
                </div>

                <div className="flex justify-end gap-2 pt-4">
                  <button
                    onClick={handleSaveGeneration}
                    className="px-3 py-2 text-xs bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
                  >
                    [ Save ]
                  </button>
                </div>
              </div>
            )}

            {activeTab === 'localModels' && (
              <div className="space-y-4">
                <div className="text-xs text-muted-foreground space-y-1">
                  <p>Download local ML models for offline processing.</p>
                  <p>Models are cached in your browser and run without API calls.</p>
                </div>

                <div className="space-y-3">
                  {models.map((model) => {
                    const downloadProgress = downloadingModels[model.id];
                    const isDownloading =
                      downloadProgress?.status === 'downloading' ||
                      downloadProgress?.status === 'loading';
                    const hasError = downloadProgress?.status === 'error';
                    const justCompleted = downloadProgress?.status === 'ready';

                    return (
                      <div
                        key={model.id}
                        className="border border-muted-foreground/30 p-3 space-y-2"
                      >
                        <div className="flex items-start justify-between">
                          <div className="flex-1">
                            <div className="flex items-center gap-2">
                              <span className="text-xs font-medium">{model.name}</span>
                              <span className="text-[10px] text-muted-foreground">
                                {model.size}
                              </span>
                              {model.isDownloaded && !isDownloading && (
                                <span className="text-[10px] px-1.5 py-0.5 bg-green-500/20 text-green-600 dark:text-green-400 rounded">
                                  READY
                                </span>
                              )}
                            </div>
                            <p className="text-[10px] text-muted-foreground mt-1">
                              {model.description}
                            </p>
                          </div>

                          <div className="flex items-center gap-2">
                            {model.isDownloaded ? (
                              <button
                                onClick={() => handleRemoveModel(model.id)}
                                className="p-1.5 text-xs hover:bg-red-500/10 text-red-500 transition-colors"
                                title="Remove model"
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                              </button>
                            ) : (
                              <button
                                onClick={() => handleDownloadModel(model.id)}
                                disabled={isDownloading}
                                className="p-1.5 text-xs hover:bg-primary/10 text-primary transition-colors disabled:opacity-50"
                                title="Download model"
                              >
                                {isDownloading ? (
                                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                ) : justCompleted ? (
                                  <Check className="h-3.5 w-3.5 text-green-500" />
                                ) : (
                                  <Download className="h-3.5 w-3.5" />
                                )}
                              </button>
                            )}
                          </div>
                        </div>

                        {/* Progress bar */}
                        {isDownloading && (
                          <div className="space-y-1">
                            <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                              <div
                                className="h-full bg-primary transition-all duration-300"
                                style={{ width: `${downloadProgress.progress}%` }}
                              />
                            </div>
                            <p className="text-[10px] text-muted-foreground">
                              Downloading... {downloadProgress.progress}%
                            </p>
                          </div>
                        )}

                        {/* Error message */}
                        {hasError && (
                          <div className="flex items-center gap-1 text-[10px] text-red-500">
                            <AlertCircle className="h-3 w-3" />
                            <span>{downloadProgress.error || 'Download failed'}</span>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>

                <div className="text-[10px] text-muted-foreground pt-2 border-t border-muted-foreground/20">
                  <p>Models are powered by ONNX Runtime and run entirely in your browser.</p>
                  <p>First download may take a while depending on your connection.</p>
                </div>

                <div className="">
                  <div className="flex gap-2">
                    <button
                      onClick={handleDeleteAllModels}
                      className="px-3 py-2 text-xs bg-red-500/10 text-red-500 hover:bg-red-500/20 transition-colors rounded-md"
                    >
                      Delete All Models
                    </button>
                    <button
                      onClick={handleClearSiteData}
                      className="px-3 py-2 text-xs border border-red-200 text-red-500 hover:bg-red-50 transition-colors rounded-md ml-auto"
                    >
                      Clear All Site Data
                    </button>
                  </div>

                  {showDeleteModelsConfirm && (
                    <div className="mt-2 p-3 bg-red-50 dark:bg-red-950/20 text-red-600 dark:text-red-400 text-xs rounded-md">
                      <p className="font-bold mb-1">Delete all models?</p>
                      <p className="mb-2">
                        This will remove all downloaded model files. You will need to download them
                        again to use local AI.
                      </p>
                      <div className="flex gap-2">
                        <button
                          onClick={() => handleDeleteAllModels()}
                          className="underline font-bold"
                        >
                          Confirm
                        </button>
                        <button
                          onClick={() => setShowDeleteModelsConfirm(false)}
                          className="underline"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  )}

                  {showClearDataConfirm && (
                    <div className="mt-2 p-3 bg-red-50 dark:bg-red-950/20 text-red-600 dark:text-red-400 text-xs rounded-md">
                      <p className="font-bold mb-1">Clear all data?</p>
                      <p className="mb-2">
                        This will wipe all settings, chats, and models. This action cannot be
                        undone.
                      </p>
                      <div className="flex gap-2">
                        <button
                          onClick={() => handleClearSiteData()}
                          className="underline font-bold"
                        >
                          Confirm Wipe
                        </button>
                        <button
                          onClick={() => setShowClearDataConfirm(false)}
                          className="underline"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {activeTab === 'interface' && (
              <div className="space-y-6">
                <div className="space-y-4">
                  <div>
                    <h3 className="text-sm font-bold mb-1">Startup Appearance</h3>
                    <p className="text-xs text-muted-foreground">
                      Customize the ASCII art shown when you start a new chat.
                    </p>
                  </div>

                  <div className="space-y-4 pt-4 border-t">
                    <h3 className="text-sm font-bold mb-1">Theme & Display</h3>

                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <Label className="text-xs font-mono">Color Theme</Label>
                        <div className="relative">
                          <select
                            value={settings.theme || 'vanilla'}
                            onChange={(e) =>
                              updateSettings({ ...settings, theme: e.target.value as any })
                            }
                            className="w-full text-xs font-mono bg-background border border-input rounded-md px-3 py-2 focus:outline-none focus:ring-1 focus:ring-primary appearance-none"
                          >
                            <option value="vanilla">vanilla</option>
                            <option value="gruvbox">gruvbox</option>
                            <option value="everforest">everforest</option>
                            <option value="tokyo-night">tokyo-night</option>
                            <option value="catppuccin">catppuccin</option>
                            <option value="solarized">solarized</option>
                            <option value="rose-pine">rose-pine</option>
                            <option value="kanagawa">kanagawa</option>
                            <option value="nord">nord</option>
                            <option value="cyberpunk">cyberpunk</option>
                          </select>
                          <div className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none text-muted-foreground text-[8px]">
                            ▼
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center justify-between border-t pt-4 border-muted-foreground/10">
                      <div className="flex items-center gap-3">
                        <div className="space-y-0.5">
                          <Label className="text-xs font-mono font-medium">Dark Mode</Label>
                          <p className="text-[10px] text-muted-foreground">
                            {settings.darkMode ? 'Dark theme enabled' : 'Light theme enabled'}
                          </p>
                        </div>
                      </div>
                      <Switch
                        checked={settings.darkMode}
                        onCheckedChange={(checked) =>
                          updateSettings({ ...settings, darkMode: checked })
                        }
                      />
                    </div>

                    <div className="flex items-center justify-between border-t pt-4 border-muted-foreground/10">
                      <div className="flex items-center gap-3">
                        <div className="space-y-0.5">
                          <Label className="text-xs font-mono font-medium">Focus Mode</Label>
                          <p className="text-[10px] text-muted-foreground">
                            {settings.focusMode ? 'UI elements hidden' : 'Standard UI view'}
                          </p>
                        </div>
                      </div>
                      <Switch
                        checked={settings.focusMode}
                        onCheckedChange={(checked) =>
                          updateSettings({ ...settings, focusMode: checked })
                        }
                      />
                    </div>
                  </div>

                  <div className="space-y-2 pt-4 border-t">
                    <Label className="text-xs font-mono">ASCII Logo Style</Label>
                    <select
                      value={settings.asciiLogo || '5'}
                      onChange={(e) => updateSettings({ ...settings, asciiLogo: e.target.value })}
                      className="w-full text-xs font-mono bg-background border border-input rounded-md px-3 py-2 focus:outline-none focus:ring-1 focus:ring-primary appearance-none"
                    >
                      <option value="random">Random (Surprise Me)</option>
                      {Object.keys(ASCII_LOGOS)
                        .filter((key) => {
                          const num = parseInt(key);
                          return num >= 1 && num <= 14;
                        })
                        .sort((a, b) => parseInt(a) - parseInt(b))
                        .map((key) => (
                          <option key={key} value={key}>
                            Style {key}
                          </option>
                        ))}
                    </select>
                  </div>

                  <div className="space-y-2">
                    <Label className="text-xs font-mono">Preview</Label>
                    <div className="p-4 border rounded-md bg-muted/20 overflow-x-auto">
                      <pre className="text-[10px] md:text-xs font-mono leading-tight whitespace-pre text-muted-foreground">
                        {settings.asciiLogo === 'random'
                          ? ASCII_LOGOS['1'] + '\n\n(Randomly selected on load)'
                          : ASCII_LOGOS[settings.asciiLogo || '5'] || ASCII_LOGOS['5']}
                      </pre>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {activeTab === 'providers' && <ProvidersTab />}
            {activeTab === 'tools' && <ToolsTab />}
            {activeTab === 'snippets' && (
              <div className="space-y-4 px-1 h-full flex flex-col">
                {editingSnippetId ? (
                  <div className="space-y-4 flex-1 flex flex-col">
                    <div className="flex items-center justify-between">
                      <h3 className="text-xs font-semibold uppercase tracking-wider">
                        {editingSnippetId === 'new' ? 'New Snippet' : 'Edit Snippet'}
                      </h3>
                      <button
                        onClick={() => setEditingSnippetId(null)}
                        className="text-xs text-muted-foreground hover:text-foreground"
                      >
                        [ Cancel ]
                      </button>
                    </div>

                    <div className="space-y-2">
                      <Label className="text-xs font-mono">Title</Label>
                      <Input
                        value={snippetTitle}
                        onChange={(e) => setSnippetTitle(e.target.value)}
                        className="text-xs font-mono"
                        placeholder="e.g. Legal Disclaimer"
                      />
                    </div>

                    <div className="space-y-2 flex-1 flex flex-col">
                      <Label className="text-xs font-mono">Content</Label>
                      <textarea
                        value={snippetContent}
                        onChange={(e) => setSnippetContent(e.target.value)}
                        className="flex-1 w-full p-3 text-xs font-mono bg-background border rounded-md resize-none focus:outline-none focus:ring-1 focus:ring-primary min-h-[150px]"
                        placeholder="Enter prompt text..."
                      />
                    </div>

                    <div className="pt-2 flex justify-end">
                      <button
                        onClick={handleSaveSnippet}
                        className="px-3 py-2 text-xs bg-primary text-primary-foreground hover:bg-primary/90 transition-colors rounded-sm"
                      >
                        [ Save Snippet ]
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="space-y-4">
                    <div className="flex justify-between items-center">
                      <p className="text-xs text-muted-foreground">Save frequently used prompts.</p>
                      <button
                        onClick={handleCreateSnippet}
                        className="px-2 py-1.5 text-xs border border-input hover:bg-muted transition-colors rounded-sm flex items-center gap-1"
                      >
                        <Plus className="h-3 w-3" /> New
                      </button>
                    </div>

                    <div className="space-y-2">
                      {snippets.length === 0 ? (
                        <div className="text-center py-8 text-muted-foreground text-xs border border-dashed rounded-md">
                          No snippets saved yet.
                        </div>
                      ) : (
                        snippets.map((snippet) => (
                          <div
                            key={snippet.id}
                            className="p-3 border rounded-md hover:bg-muted/30 transition-colors flex justify-between items-start group"
                          >
                            <div className="flex-1 min-w-0 pr-3">
                              <h4 className="text-xs font-medium truncate">{snippet.title}</h4>
                              <p className="text-[10px] text-muted-foreground line-clamp-2 font-mono mt-1 opacity-70">
                                {snippet.content}
                              </p>
                            </div>
                            <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                              <button
                                onClick={() => handleEditSnippet(snippet)}
                                className="p-1.5 hover:bg-muted rounded text-muted-foreground hover:text-foreground"
                                title="Edit"
                              >
                                <Edit2 className="h-3.5 w-3.5" />
                              </button>
                              <button
                                onClick={() => handleDeleteSnippet(snippet.id)}
                                className="p-1.5 hover:bg-red-50 dark:hover:bg-red-900/20 rounded text-muted-foreground hover:text-red-500"
                                title="Delete"
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                              </button>
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}
            {activeTab === 'developer' && (
              <div className="space-y-4 h-full flex flex-col px-1">
                <div className="space-y-2 flex-1 flex flex-col">
                  <Label className="text-xs font-mono">Junas Configuration (TOML)</Label>
                  <p className="text-[10px] text-muted-foreground">
                    Paste your junas.toml script here to configure everything at once.
                  </p>
                  <textarea
                    value={tomlContent}
                    onChange={(e) => setTomlContent(e.target.value)}
                    className="flex-1 w-full p-3 text-xs font-mono bg-background border rounded-md resize-none focus:outline-none focus:ring-1 focus:ring-primary min-h-[300px]"
                    spellCheck={false}
                  />
                </div>
                <div className="flex justify-end gap-2">
                  <button
                    onClick={handleSaveToml}
                    className="px-3 py-2 text-xs bg-primary text-primary-foreground hover:bg-primary/90 transition-colors rounded-sm"
                  >
                    [ Apply Configuration ]
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </DialogContent>

      <AlertDialog open={showDeleteModelsConfirm} onOpenChange={setShowDeleteModelsConfirm}>
        <AlertDialogContent className="font-mono">
          <AlertDialogHeader>
            <AlertDialogTitle>Delete all local models?</AlertDialogTitle>
            <AlertDialogDescription>
              This will remove all downloaded model files from your device to free up disk space.
              You will need to download them again to use local AI features.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="text-xs">Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteAllModels}
              className="bg-red-600 hover:bg-red-700 text-xs"
            >
              Delete Models
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={showClearDataConfirm} onOpenChange={setShowClearDataConfirm}>
        <AlertDialogContent className="font-mono">
          <AlertDialogHeader>
            <AlertDialogTitle>Clear all site data?</AlertDialogTitle>
            <AlertDialogDescription>
              This action cannot be undone. This will permanently delete your chat history,
              settings, API keys, and local models.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="text-xs">Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleClearSiteData}
              className="bg-red-600 hover:bg-red-700 text-xs"
            >
              Clear Everything
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Dialog>
  );
}
