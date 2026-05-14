import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { ChatSettings } from '@/types/chat';
import { User, Zap } from 'lucide-react';

interface UserSettingsProps {
  settings: ChatSettings;
  onSettingChange: (key: keyof ChatSettings, value: any) => void;
}

export function UserSettings({ settings, onSettingChange }: UserSettingsProps) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <User className="h-5 w-5 text-muted-foreground" />
          <CardTitle>User Preferences</CardTitle>
        </div>
        <CardDescription>
          Personalize your experience with Junas
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="space-y-2">
          <Label htmlFor="user-name">Your Name (Optional)</Label>
          <Input
            id="user-name"
            type="text"
            placeholder="Enter your name"
            value={settings.userName || ''}
            onChange={(e) => onSettingChange('userName', e.target.value)}
            className="max-w-md text-xs h-8"
          />
          <p className="text-[10px] text-muted-foreground">
            Junas will greet you by name when you start a conversation
          </p>
        </div>

        <div className="pt-4 border-t space-y-4">
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <div className="flex items-center gap-2">
                <Zap className="h-4 w-4 text-primary" />
                <Label className="text-sm font-semibold">Agent Mode</Label>
              </div>
              <p className="text-[10px] text-muted-foreground">
                Allow Junas to autonomously chain multiple tool calls to achieve complex goals.
              </p>
            </div>
            <Switch
              checked={settings.agentMode}
              onCheckedChange={(checked) => onSettingChange('agentMode', checked)}
            />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
