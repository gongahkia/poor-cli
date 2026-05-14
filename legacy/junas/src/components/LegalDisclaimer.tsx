'use client'

import { useState } from "react"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog"
import { StorageManager } from "@/lib/storage"

interface LegalDisclaimerProps {
  onDismiss?: () => void;
}

export function LegalDisclaimerContent() {
  return (
    <div className="font-mono text-xs space-y-3">
      <p>
        <strong>&gt; Important:</strong> Junas is an AI-powered assistant and does not provide legal advice.
        The information provided is for general informational purposes only and should not be relied upon
        as a substitute for professional legal counsel.
      </p>
      <p>
        For specific legal matters, please consult a qualified lawyer licensed to practice in Singapore.
        By using Junas, you acknowledge that AI-generated responses may contain errors or inaccuracies.
      </p>
      <p>
        <strong>&gt; No Attorney-Client Relationship:</strong> Use of this service does not create an attorney-client
        relationship between you and the developers or operators of Junas. Any information you provide is not
        protected by attorney-client privilege.
      </p>
      <p>
        <strong>&gt; Accuracy and Reliability:</strong> While we strive to provide accurate information, AI models
        can make mistakes, misinterpret context, or provide outdated information. Always verify critical legal
        information with authoritative sources or qualified legal professionals.
      </p>
      <p>
        <strong>&gt; Limitation of Liability:</strong> To the fullest extent permitted by law, we disclaim all
        liability for any damages arising from your use of or reliance on information provided by Junas.
        This includes, but is not limited to, direct, indirect, incidental, consequential, or punitive damages.
      </p>
    </div>
  );
}

export function LegalDisclaimer({ onDismiss }: LegalDisclaimerProps = {}) {
  const [isOpen, setIsOpen] = useState(() => {
    if (typeof window !== 'undefined') {
      // Show disclaimer only if user hasn't seen it before
      return !StorageManager.hasSeenDisclaimer()
    }
    return true
  })

  const handleAccept = () => {
    setIsOpen(false)
    StorageManager.setDisclaimerSeen()
    if (onDismiss) {
      onDismiss()
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={() => {}}>
      <DialogContent
        className="sm:max-w-[500px] font-mono"
        onPointerDownOutside={(e) => e.preventDefault()}
        onEscapeKeyDown={(e) => e.preventDefault()}
      >
        <DialogHeader>
          <DialogTitle className="text-sm">
            Legal Disclaimer
          </DialogTitle>
          <div className="text-sm text-muted-foreground text-left pt-2">
            <LegalDisclaimerContent />
          </div>
        </DialogHeader>
        <DialogFooter>
          <button
            onClick={handleAccept}
            className="w-full sm:w-auto px-4 py-2 text-xs bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            [ I Agree ]
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
