# ClawReel Pipeline Optimization Design

> Date: 2026-04-11
> Status: Approved
> Scope: SKILL.md + code (format, align, segment_aligner)

## Background

During the "OpenClaw vs Hermes Agent" video production session, 6 issues were identified:

| # | Problem | Severity | Root Cause |
|---|---------|----------|------------|
| P1 | Hook text spoken twice by TTS | High | `sentences[0:2]` identical to `hooks`, align processes both |
| P2 | `# title` read aloud by TTS | High | format includes `# title\n` as part of sentences[0] |
| P3 | align hardcodes edge provider | Medium | cli.py:298 `provider="edge"` (fixed during session) |
| P4 | Audio-subtitle desync | High | Segment-based uniform estimation inaccurate |
| P5 | 30-sentence limit too low | Low | Natural speech scripts exceed limit |
| P6 | First segment/transition too short | Low | Short hook text gets same duration as long sentences |

## Design Decisions

### D1: format output — separate title from sentences

**Current**: format puts `# title\nsentence` as sentences[0]
**New**: sentences[0] is pure speech text, no `#` prefix

```json
{
  "title": "2026 AI Agent Showdown",
  "sentences": ["First sentence", "Second sentence", ...],
  "hooks": ["First sentence", "Second sentence"],
  "cta": "Last sentence"
}
```

- `sentences[0]` = first spoken sentence, no `#` prefix
- `hooks` = auto-derived from sentences[0] and sentences[1]
- `script` field retains original format for archival

**Files**: `cli.py` cmd_format (~30 lines)

### D2: align command — hook dedup + char-weighted timing

**A. Defensive hook dedup**: After reading script JSON, strip any sentences that duplicate hooks:

```python
if hooks_text and sentences:
    while (sentences and hooks_text
           and clean_str(sentences[0]) == clean_str(hooks_text[0])):
        sentences.pop(0)
        hooks_text.pop(0)
```

This handles both old-format (sentences contains hooks) and new-format scripts.

**B. `--provider` and `--voice` passthrough**: Already fixed `--provider`. Make `--voice` default read from config instead of hardcoding `zh-CN-XiaoxiaoNeural`.

**C. Char-weighted duration estimation for MiniMax fallback**:

```python
# Before: uniform split
per_sent = avail / len(sentences)

# After: char-weighted split
total_chars = sum(len(s) for s in sentences)
per_sent = (len(sent) / total_chars) * avail
```

Long sentences get more time, short hooks get less — solves P6.

**D. MAX_SENTENCE_COUNT raised from 30 to 40**: Natural speech scripts with 30+ sentences are common.

**Files**: `cli.py` cmd_align, `segment_aligner.py` align_segments (~60 lines combined)

### D3: SKILL.md — anti-patterns + workflow updates

**A. New "Anti-Patterns" section** after General Rules:

| Anti-Pattern | Consequence | Correct Approach |
|-------------|-------------|-----------------|
| sentences contains `# title` prefix | TTS reads "hashtag title" | sentences = pure speech, title stored separately |
| sentences[0:2] duplicates hooks | First sentences spoken twice | format auto-separates, Agent doesn't manually duplicate |
| `--text` includes hook text | Same as above | `--text` = body only, hooks read from script |
| Segments JSON for subtitles | Audio-subtitle desync | Default to Whisper `burn-subs` |
| edge TTS for all content | Robotic voice | Use `--provider minimax` for natural sound |
| Chinese text in image prompts | Garbled AI-generated text | Image text always in English |

**B. Phase 2 update**: Emphasize `# title` is archival only, not spoken.

**C. Phase 4 update**:
- `--text` description: "body text only (no hooks, no `#` title)"
- Recommend `--provider minimax` for natural voice
- `--voice` optional, default from config

**D. Phase 7 update**:
- Default: `burn-subs --model medium` (Whisper)
- Segments JSON subtitles as fallback, labeled "may desync"

**E. Data verification reminder**: After Phase 2, prompt: "For specific numbers (star counts, percentages), prefer real-time data from GitHub API / official sources."

**Files**: SKILL.md only

## Implementation Order

1. `segment_aligner.py` — char-weighted timing + MAX limit raise
2. `cli.py` cmd_format — strip `#` from sentences
3. `cli.py` cmd_align — hook dedup + voice default from config
4. SKILL.md — anti-patterns section + Phase 2/4/7 updates

## Risk Assessment

| Change | Risk | Mitigation |
|--------|------|------------|
| format output change | Existing scripts may expect `#` in sentences[0] | Defensive strip in align handles both formats |
| Char-weighted timing | Edge case: very long sentences get too much time | Cap per-sentence at 15s |
| MAX limit 30→40 | More segments = more memory in compose | compose already handles 30+, no issue |

## Verification Plan

1. Run format with test content, verify no `#` in sentences
2. Run align with old-format script (sentences has `#`), verify dedup works
3. Run align with minimax, verify char-weighted timing (long sentences > short)
4. Produce a full video with new pipeline, compare with previous output
