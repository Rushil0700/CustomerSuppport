---
id: troubleshooting-sync-stuck
title: Files stuck in Syncing
category: troubleshooting
tags: [files, stuck, sync, troubleshooting]
audience: customer
severity: normal
---

# Files stuck in "Syncing"

## Symptom

One or more files show the spinning sync badge for more than 15 minutes and the
activity feed shows no progress.

## Most common causes, in order

1. **A file is open and locked by another program.** Office and Adobe apps hold
   exclusive locks. Close the app and the transfer resumes within a minute.
2. **A path is too long.** Windows rejects paths over 260 characters. Shorten a
   parent folder name.
3. **An unsupported character in the name.** `\ / : * ? " < > |` are rejected by
   at least one supported platform and block the whole batch.
4. **The workspace is over quota.** Check Settings > Usage. Sync pauses entirely
   when storage is exhausted.

## Steps

1. Open **Activity > Errors** and read the first failing item; the rest of the
   queue is usually blocked behind it.
2. Resolve that item using the causes above.
3. Choose **Pause sync**, wait ten seconds, then **Resume sync**.
4. If nothing moves, sign out and back in. This rebuilds the local index without
   touching your files.

## Verify

The badge turns to a green check and Activity shows the file's completion time.

## Escalate

Escalate when the workspace is under quota, no error is listed, and a pause and
resume plus a re-login all leave the same file pending - that pattern indicates a
server-side index problem.
