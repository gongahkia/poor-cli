import { useEffect, useState } from 'react';
import { ASCII_LOGOS } from '@/lib/ascii-logos';
import { StorageManager } from '@/lib/storage';

interface IntroAnimationProps {
  onComplete: () => void;
}

const IntroAnimation = ({ onComplete }: IntroAnimationProps) => {
  const [lines, setLines] = useState<string[]>([]);
  const [lineCharCounts, setLineCharCounts] = useState<number[]>([]);
  const [fadeOut, setFadeOut] = useState(false);
  const [readyToFade, setReadyToFade] = useState(false);

  useEffect(() => {
    // Load logo preference
    const settings = StorageManager.getSettings();
    let logoKey = settings.asciiLogo || '5';

    if (logoKey === 'random') {
      const keys = Object.keys(ASCII_LOGOS);
      logoKey = keys[Math.floor(Math.random() * keys.length)];
    }

    const selectedLogo = ASCII_LOGOS[logoKey] || ASCII_LOGOS['5'];
    const splitLines = selectedLogo.split('\n');
    setLines(splitLines);
    setLineCharCounts(Array(splitLines.length).fill(0));
  }, []);

  useEffect(() => {
    if (lines.length === 0) return;

    const lineTimers: NodeJS.Timeout[] = [];
    const charIntervals: NodeJS.Timeout[] = [];

    lines.forEach((line, i) => {
      const lineTimer = setTimeout(() => {
        let charIdx = 0;
        const charInterval = setInterval(() => {
          charIdx++;
          setLineCharCounts((prev) => {
            const next = [...prev];
            // Safety check in case lines changed
            if (i < next.length) {
              next[i] = Math.min(charIdx, line.length);
            }
            return next;
          });
          if (charIdx >= line.length) {
            clearInterval(charInterval);
            // If this is the last line, allow fade out trigger
            if (i === lines.length - 1) {
              setTimeout(() => setReadyToFade(true), 200); // Small pause for polish
            }
          }
        }, 20);
        charIntervals.push(charInterval);
      }, i * 300);
      lineTimers.push(lineTimer);
    });

    return () => {
      lineTimers.forEach(clearTimeout);
      charIntervals.forEach(clearInterval);
    };
  }, [lines]);

  // Handler for user interaction to trigger fade out
  useEffect(() => {
    if (!readyToFade) return;

    const handle = (e: KeyboardEvent | MouseEvent) => {
      if (fadeOut) return;
      if (e instanceof KeyboardEvent && e.code !== 'Space') return;

      setFadeOut(true);
      // Wait for fade out animation to complete
      setTimeout(onComplete, 200);
    };

    window.addEventListener('mousedown', handle);
    window.addEventListener('keydown', handle);
    return () => {
      window.removeEventListener('mousedown', handle);
      window.removeEventListener('keydown', handle);
    };
  }, [readyToFade, fadeOut, onComplete]);

  return (
    <div
      className={`fixed inset-0 z-50 flex items-center justify-center bg-background text-foreground transition-opacity ${fadeOut ? 'duration-200' : 'duration-500'} ${fadeOut ? 'fade-out' : 'fade-in'}`}
    >
      <div className="flex flex-col items-center text-center">
        <pre className="text-[0.5rem] leading-[0.6rem] md:text-xs font-mono whitespace-pre">
          {lines.map((line, i) => line.substring(0, lineCharCounts[i])).join('\n')}
        </pre>
        {readyToFade && !fadeOut && (
          <>
            <div className="mt-2 text-[10px] font-mono text-muted-foreground opacity-50">
              v2.0.0
            </div>
            <div className="mt-8 text-xs font-mono text-muted-foreground select-none pointer-events-none animate-pulse">
              [ Click or press <b>Space</b> to continue ]
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default IntroAnimation;
