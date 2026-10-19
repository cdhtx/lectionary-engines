"""
Shared formatting instructions for the three study engines.

Appended to each engine's SYSTEM_PROMPT. Everything here is plain markdown
(blockquotes with a bold label), so a study that ignores it still renders.
The labels are matched by web/services/study_callouts.py.
"""

STUDY_FORMAT_BLOCK = """

### FORMAT FOR SKIMMING (does not change the content, length, or structure above)

Readers skim before they read. Keep every idea, quotation, and word-count target above. Change only how it is laid out:

- Do NOT add, rename, or reorder any headings. Use only the headings the structure above already calls for.
- Open each major section with one callout: a blockquote that starts with a bold label, on a single line:
  > **Key insight:** one or two plain sentences that carry the section's main point.
- Once or twice in the whole study, set apart the single sharpest sentence as a pull quote:
  > **Core line:** the sentence, exactly as you would want it quoted.
- Where you ask the reader to do or face something, use a callout instead of a paragraph:
  > **Try this:** one specific, doable action.
  > **Sit with this:** one uncomfortable question.
- Quote Scripture in plain blockquotes (no label), as you already do.
- When you list evidence, parallels, steps, or options, use bullets with a short bold lead-in instead of one long paragraph.
- Keep paragraphs short. Break up anything over five sentences.
- Put prose between callouts so two callouts never sit back to back.
- Use these four labels exactly: Key insight, Core line, Try this, Sit with this. Invent no others.
"""
